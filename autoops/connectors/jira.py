from __future__ import annotations

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


JIRA_SOURCE_TYPE = "jira"
DEFAULT_CONNECTION_ID = "jira-fixture"


class JiraFixtureConnector:
    source_type = JIRA_SOURCE_TYPE

    def __init__(
        self,
        fixture_root: Path = DEFAULT_FIXTURE_ROOT,
        connection_id: str = DEFAULT_CONNECTION_ID,
        allowed_key_prefixes: tuple[str, ...] = ("INC-", "OPS-", "CHG-"),
        live: bool = False,
    ) -> None:
        self.fixture_root = fixture_root
        self.connection_id = connection_id
        self.allowed_key_prefixes = allowed_key_prefixes
        self.live = live
        self.mode = "live" if live else "fixture"

    def validate_connection(self) -> ValidationResult:
        if self.live:
            return ValidationResult(
                ok=False,
                mode=self.mode,
                message=(
                    "Live Jira mode is not implemented in Gate 6. "
                    "Stop and complete project, token, scope, and allowlist setup before enabling it."
                ),
            )
        if not (self.fixture_root / "jira").exists():
            return ValidationResult(False, self.mode, f"Missing Jira fixtures under {self.fixture_root}.")
        return ValidationResult(True, self.mode, "Jira fixture connection is available.")

    def fetch_changes(self, cursor: str | None = None) -> FetchResult:
        del cursor
        records: list[RawRecord] = []
        for path in sorted((self.fixture_root / "jira").glob("*.json")):
            payload = load_fixture(path)
            key = str(payload["key"])
            if not key.startswith(self.allowed_key_prefixes):
                continue
            fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else {}
            raw = json.dumps(payload, sort_keys=True)
            records.append(
                RawRecord(
                    source_type=self.source_type,
                    external_id=key,
                    external_url=_optional_str(payload.get("self")),
                    external_version=_optional_str(fields.get("updated")),
                    external_created_at=_jira_time(fields.get("created")),
                    external_updated_at=_jira_time(fields.get("updated")),
                    payload_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                    payload=payload,
                    fixture_path=path,
                )
            )
        next_cursor = max((record.external_updated_at or "" for record in records), default="") or None
        return FetchResult(records=records, next_cursor=next_cursor)

    def normalize(self, raw_record: RawRecord) -> dict[str, Any]:
        payload = raw_record.payload
        fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else {}
        issue_type = fields.get("issuetype") if isinstance(fields.get("issuetype"), dict) else {}
        status = fields.get("status") if isinstance(fields.get("status"), dict) else {}
        components = fields.get("components") if isinstance(fields.get("components"), list) else []
        labels = [str(label) for label in fields.get("labels", []) if label]
        component = _first_component(components)
        content = _description_text(fields.get("description"))
        status_name = _optional_str(status.get("name"))
        issue_type_name = _optional_str(issue_type.get("name"))
        summary = str(fields.get("summary") or payload["key"])
        normalized = {
            "source_type": self.source_type,
            "source_id": _source_id(str(payload["key"])),
            "source_url": raw_record.external_url,
            "title": summary,
            "service": _service_from_labels(labels) or component,
            "component": component,
            "alert_name": None,
            "ticket_id": str(payload["key"]),
            "created_at": raw_record.external_created_at,
            "updated_at": raw_record.external_updated_at or _now(),
            "version": raw_record.external_version,
            "deprecated": False,
            "tags": labels + [value for value in (issue_type_name, status_name) if value],
            "author": None,
            "owner_contact": None,
            "content": " ".join(value for value in (summary, issue_type_name, status_name, content) if value),
        }
        if not normalized["content"]:
            raise ValueError(f"Jira issue has no supported content: {raw_record.external_id}")
        return normalized


def sync_jira_fixture(db_path: Path, fixture_root: Path = DEFAULT_FIXTURE_ROOT, dry_run: bool = False) -> SyncResult:
    connector = JiraFixtureConnector(fixture_root=fixture_root)
    validation = connector.validate_connection()
    if not validation.ok:
        return SyncResult(connector.connection_id, connector.source_type, connector.mode, dry_run, 0, 0, 0, 0, 0, "error", validation.message)

    fetched = connector.fetch_changes()
    if dry_run:
        return SyncResult(connector.connection_id, connector.source_type, connector.mode, True, fetched.records_seen, fetched.records_seen, fetched.records_seen, 0, 0, "dry_run", "Validated Jira fixture records without writing to SQLite.")

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
                "display_name": "Jira Fixture",
                "enabled": True,
                "base_url": "mock://jira",
                "scope_description": "Fixture-only read scope for Jira issue records.",
            },
        )
        for record in fetched.records:
            source_path = str(record.fixture_path) if record.fixture_path else None
            raw = json.dumps(record.payload, sort_keys=True)
            safety = check_content_safety(raw)
            if not safety.allowed:
                blocked += 1
                insert_audit_event(conn, _audit_event("connector_record_blocked", source_path, "blocked", "Raw Jira fixture failed safety gate.", now))
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
                insert_audit_event(conn, _audit_event("connector_record_blocked", source_path, "blocked", "Normalized Jira content failed safety gate.", now))
                continue

            document = _document_from_payload(normalized, source_path or record.external_id, normalized_raw, now)
            replace_document(conn, document)
            for index, chunk_text in enumerate(_chunk_text(str(normalized["content"]))):
                insert_chunk(conn, _chunk_from_document(document, chunk_text, index))
            indexed += 1
            insert_audit_event(conn, _audit_event("connector_document_indexed", source_path, "indexed", f"Indexed Jira issue {record.external_id}.", now))

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

    return SyncResult(connector.connection_id, connector.source_type, connector.mode, False, fetched.records_seen, changed, indexed, 0, blocked, "success", "Synced Jira fixture records to SQLite.")


def _description_text(node: Any) -> str:
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        parts: list[str] = []
        if node.get("type") == "text" and node.get("text"):
            parts.append(str(node["text"]))
        for child in node.get("content", []):
            text = _description_text(child)
            if text:
                parts.append(text)
        return " ".join(parts)
    if isinstance(node, list):
        return " ".join(text for item in node if (text := _description_text(item)))
    return ""


def _first_component(components: list[Any]) -> str | None:
    for component in components:
        if isinstance(component, dict) and component.get("name"):
            return str(component["name"])
    return None


def _service_from_labels(labels: list[str]) -> str | None:
    for label in labels:
        if label in {"payments", "checkout", "search", "orders"}:
            return label
    return None


def _jira_time(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    if value.endswith("+0000"):
        return f"{value[:-5]}Z"
    return value


def _source_id(key: str) -> str:
    return f"jira:{key}"


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
