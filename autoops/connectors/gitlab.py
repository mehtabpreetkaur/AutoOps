from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from autoops.fixtures import DEFAULT_FIXTURE_ROOT, load_fixture
from autoops.ingest import _audit_event, _chunk_from_document, _chunk_text, _document_from_payload
from autoops.safety import check_content_safety
from autoops.storage import (
    connect,
    initialize,
    insert_audit_event,
    insert_chunk,
    record_raw_source_record,
    replace_document,
    upsert_source_connection,
    upsert_sync_state,
)

from .base import FetchResult, RawRecord, SyncResult, ValidationResult


GITLAB_SOURCE_TYPE = "gitlab"
DEFAULT_CONNECTION_ID = "gitlab-fixture"


class GitLabFixtureConnector:
    source_type = GITLAB_SOURCE_TYPE

    def __init__(
        self,
        fixture_root: Path = DEFAULT_FIXTURE_ROOT,
        connection_id: str = DEFAULT_CONNECTION_ID,
        allowed_paths: tuple[str, ...] = ("runbooks/",),
        live: bool = False,
    ) -> None:
        self.fixture_root = fixture_root
        self.connection_id = connection_id
        self.allowed_paths = allowed_paths
        self.live = live
        self.mode = "live" if live else "fixture"

    def validate_connection(self) -> ValidationResult:
        if self.live:
            return ValidationResult(
                ok=False,
                mode=self.mode,
                message=(
                    "Live GitLab mode is not implemented in Gate 6. "
                    "Stop and complete project, token, scope, and allowlist setup before enabling it."
                ),
            )
        if not (self.fixture_root / "gitlab").exists():
            return ValidationResult(False, self.mode, f"Missing GitLab fixtures under {self.fixture_root}.")
        return ValidationResult(True, self.mode, "GitLab fixture connection is available.")

    def fetch_changes(self, cursor: str | None = None) -> FetchResult:
        del cursor
        records: list[RawRecord] = []
        for path in sorted((self.fixture_root / "gitlab").glob("*.json")):
            payload = load_fixture(path)
            file_path = str(payload["file_path"])
            if not file_path.startswith(self.allowed_paths):
                continue
            raw = json.dumps(payload, sort_keys=True)
            records.append(
                RawRecord(
                    source_type=self.source_type,
                    external_id=file_path,
                    external_url=f"mock://gitlab/{file_path}",
                    external_version=_optional_str(payload.get("last_commit_id") or payload.get("commit_id")),
                    external_created_at=None,
                    external_updated_at=None,
                    payload_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                    payload=payload,
                    fixture_path=path,
                )
            )
        next_cursor = max((record.external_version or "" for record in records), default="") or None
        return FetchResult(records=records, next_cursor=next_cursor)

    def normalize(self, raw_record: RawRecord) -> dict[str, Any]:
        payload = raw_record.payload
        content = _decode_content(payload)
        file_path = str(payload["file_path"])
        title = str(payload.get("file_name") or file_path.rsplit("/", 1)[-1])
        labels = ["gitlab", str(payload.get("ref", "HEAD"))]
        normalized = {
            "source_type": self.source_type,
            "source_id": _source_id(file_path),
            "source_url": raw_record.external_url,
            "title": title,
            "service": _service_from_path(file_path),
            "component": None,
            "alert_name": None,
            "created_at": None,
            "updated_at": _now(),
            "version": raw_record.external_version,
            "deprecated": False,
            "tags": labels,
            "author": None,
            "owner_contact": None,
            "content": content,
        }
        if not normalized["content"]:
            raise ValueError(f"GitLab file has no supported content: {raw_record.external_id}")
        return normalized


def sync_gitlab_fixture(db_path: Path, fixture_root: Path = DEFAULT_FIXTURE_ROOT, dry_run: bool = False) -> SyncResult:
    connector = GitLabFixtureConnector(fixture_root=fixture_root)
    return _sync_fixture_connector(
        connector=connector,
        db_path=db_path,
        dry_run=dry_run,
        display_name="GitLab Fixture",
        base_url="mock://gitlab",
        scope_description="Fixture-only read scope for GitLab repository file records.",
    )


def _sync_fixture_connector(
    connector: GitLabFixtureConnector,
    db_path: Path,
    dry_run: bool,
    display_name: str,
    base_url: str,
    scope_description: str,
) -> SyncResult:
    validation = connector.validate_connection()
    if not validation.ok:
        return SyncResult(connector.connection_id, connector.source_type, connector.mode, dry_run, 0, 0, 0, 0, 0, "error", validation.message)

    fetched = connector.fetch_changes()
    if dry_run:
        return SyncResult(
            connector.connection_id,
            connector.source_type,
            connector.mode,
            True,
            fetched.records_seen,
            fetched.records_seen,
            fetched.records_seen,
            0,
            0,
            "dry_run",
            "Validated GitLab fixture records without writing to SQLite.",
        )

    conn = connect(db_path)
    now = _now()
    changed = 0
    indexed = 0
    blocked = 0
    try:
        initialize(conn)
        upsert_source_connection(
            conn,
            {
                "connection_id": connector.connection_id,
                "source_type": connector.source_type,
                "display_name": display_name,
                "enabled": True,
                "base_url": base_url,
                "scope_description": scope_description,
            },
        )
        for record in fetched.records:
            source_path = str(record.fixture_path) if record.fixture_path else None
            raw = json.dumps(record.payload, sort_keys=True)
            safety = check_content_safety(raw)
            if not safety.allowed:
                blocked += 1
                insert_audit_event(conn, _audit_event("connector_record_blocked", source_path, "blocked", "Raw GitLab fixture failed safety gate.", now))
                continue

            inserted = record_raw_source_record(
                conn,
                {
                    "connection_id": connector.connection_id,
                    "source_type": record.source_type,
                    "external_id": record.external_id,
                    "external_url": record.external_url,
                    "external_version": record.external_version,
                    "external_created_at": record.external_created_at,
                    "external_updated_at": record.external_updated_at,
                    "payload_hash": record.payload_hash,
                    "payload_storage_mode": "hash_only",
                    "deleted_or_archived": False,
                },
            )
            if not inserted:
                continue

            changed += 1
            normalized = connector.normalize(record)
            normalized_raw = json.dumps(normalized, sort_keys=True)
            normalized_safety = check_content_safety(normalized_raw)
            if not normalized_safety.allowed:
                blocked += 1
                insert_audit_event(conn, _audit_event("connector_record_blocked", source_path, "blocked", "Normalized GitLab content failed safety gate.", now))
                continue

            document = _document_from_payload(normalized, source_path or record.external_id, normalized_raw, now)
            replace_document(conn, document)
            for index, chunk_text in enumerate(_chunk_text(str(normalized["content"]))):
                insert_chunk(conn, _chunk_from_document(document, chunk_text, index))
            indexed += 1
            insert_audit_event(conn, _audit_event("connector_document_indexed", source_path, "indexed", f"Indexed GitLab file {record.external_id}.", now))

        upsert_sync_state(
            conn,
            {
                "connection_id": connector.connection_id,
                "sync_cursor": fetched.next_cursor,
                "last_successful_sync_at": now,
                "last_attempted_sync_at": now,
                "last_status": "success",
                "last_error": None,
                "records_seen": fetched.records_seen,
                "records_changed": changed,
            },
        )
        conn.commit()
    finally:
        conn.close()

    return SyncResult(connector.connection_id, connector.source_type, connector.mode, False, fetched.records_seen, changed, indexed, 0, blocked, "success", "Synced GitLab fixture records to SQLite.")


def _decode_content(payload: dict[str, Any]) -> str:
    content = payload.get("content")
    if not isinstance(content, str):
        return ""
    if payload.get("encoding") == "base64":
        return base64.b64decode(content).decode("utf-8")
    return content


def _service_from_path(file_path: str) -> str | None:
    parts = file_path.split("/")
    if len(parts) >= 3 and parts[0] == "runbooks":
        return parts[1]
    return None


def _source_id(file_path: str) -> str:
    return f"gitlab:{file_path}"


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
