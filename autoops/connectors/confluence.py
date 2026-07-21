from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from autoops.fixtures import DEFAULT_FIXTURE_ROOT, load_fixture
from autoops.ingest import _audit_event, _chunk_from_document, _chunk_text, _document_from_payload
from autoops.safety import check_content_safety
from autoops.storage import (
    connect,
    delete_document,
    initialize,
    insert_audit_event,
    insert_chunk,
    record_raw_source_record,
    replace_document,
    upsert_source_connection,
    upsert_sync_state,
)

from .base import FetchResult, RawRecord, SyncResult, ValidationResult


CONFLUENCE_SOURCE_TYPE = "confluence"
DEFAULT_CONNECTION_ID = "confluence-fixture"


class ConfluenceFixtureConnector:
    source_type = CONFLUENCE_SOURCE_TYPE

    def __init__(
        self,
        fixture_root: Path = DEFAULT_FIXTURE_ROOT,
        connection_id: str = DEFAULT_CONNECTION_ID,
        allowed_space_ids: set[str] | None = None,
        live: bool = False,
    ) -> None:
        self.fixture_root = fixture_root
        self.connection_id = connection_id
        self.allowed_space_ids = allowed_space_ids or {"space-autoops"}
        self.live = live
        self.mode = "live" if live else "fixture"

    def validate_connection(self) -> ValidationResult:
        if self.live:
            return ValidationResult(
                ok=False,
                mode=self.mode,
                message=(
                    "Live Confluence mode is not implemented in Gate 4. "
                    "Stop and complete platform account, token, scope, and allowlist setup before enabling it."
                ),
            )
        if not (self.fixture_root / "confluence").exists():
            return ValidationResult(False, self.mode, f"Missing Confluence fixtures under {self.fixture_root}.")
        return ValidationResult(True, self.mode, "Confluence fixture connection is available.")

    def fetch_changes(self, cursor: str | None = None) -> FetchResult:
        del cursor
        records: list[RawRecord] = []
        for path in sorted((self.fixture_root / "confluence").glob("*.json")):
            payload = load_fixture(path)
            if str(payload.get("spaceId")) not in self.allowed_space_ids:
                continue
            raw = json.dumps(payload, sort_keys=True)
            version = payload.get("version") if isinstance(payload.get("version"), dict) else {}
            links = payload.get("_links") if isinstance(payload.get("_links"), dict) else {}
            records.append(
                RawRecord(
                    source_type=self.source_type,
                    external_id=str(payload["id"]),
                    external_url=_join_url(links.get("base"), links.get("webui")),
                    external_version=str(version.get("number")) if version.get("number") is not None else None,
                    external_created_at=_optional_str(payload.get("createdAt")),
                    external_updated_at=_optional_str(version.get("createdAt")),
                    payload_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                    payload=payload,
                    deleted_or_archived=payload.get("status") in {"archived", "deleted"},
                    fixture_path=path,
                )
            )
        latest = max((record.external_updated_at or "" for record in records), default="") or None
        return FetchResult(records=records, next_cursor=latest)

    def normalize(self, raw_record: RawRecord) -> dict[str, Any]:
        payload = raw_record.payload
        version = payload.get("version") if isinstance(payload.get("version"), dict) else {}
        labels = _labels(payload)
        content = _body_text(payload)
        normalized = {
            "source_type": self.source_type,
            "source_id": _source_id(raw_record.external_id),
            "source_url": raw_record.external_url,
            "title": str(payload["title"]),
            "service": _metadata_value(labels, "service"),
            "component": _metadata_value(labels, "component"),
            "alert_name": _metadata_value(labels, "alert"),
            "created_at": _optional_str(payload.get("createdAt")),
            "updated_at": raw_record.external_updated_at or _optional_str(payload.get("createdAt")),
            "version": str(version.get("number")) if version.get("number") is not None else None,
            "deprecated": payload.get("status") != "current",
            "tags": labels,
            "author": _optional_str(version.get("authorId") or payload.get("authorId")),
            "owner_contact": _optional_str(payload.get("ownerId")),
            "content": content,
        }
        if not normalized["content"]:
            raise ValueError(f"Confluence page has no supported body content: {raw_record.external_id}")
        return normalized


def sync_confluence_fixture(db_path: Path, fixture_root: Path = DEFAULT_FIXTURE_ROOT, dry_run: bool = False) -> SyncResult:
    connector = ConfluenceFixtureConnector(fixture_root=fixture_root)
    validation = connector.validate_connection()
    if not validation.ok:
        return SyncResult(
            connector.connection_id,
            connector.source_type,
            connector.mode,
            dry_run,
            0,
            0,
            0,
            0,
            0,
            "error",
            validation.message,
        )

    fetched = connector.fetch_changes()
    if dry_run:
        return SyncResult(
            connector.connection_id,
            connector.source_type,
            connector.mode,
            True,
            fetched.records_seen,
            fetched.records_seen,
            sum(1 for record in fetched.records if not record.deleted_or_archived),
            sum(1 for record in fetched.records if record.deleted_or_archived),
            0,
            "dry_run",
            "Validated Confluence fixture records without writing to SQLite.",
        )

    conn = connect(db_path)
    now = _now()
    changed = 0
    indexed = 0
    archived = 0
    blocked = 0
    try:
        initialize(conn)
        upsert_source_connection(
            conn,
            {
                "connection_id": connector.connection_id,
                "source_type": connector.source_type,
                "display_name": "Confluence Fixture",
                "enabled": True,
                "base_url": "mock://confluence",
                "scope_description": "Fixture-only read scope for Confluence page records.",
            },
        )
        for record in fetched.records:
            source_path = str(record.fixture_path) if record.fixture_path else None
            raw = json.dumps(record.payload, sort_keys=True)
            safety = check_content_safety(raw)
            if not safety.allowed:
                blocked += 1
                insert_audit_event(
                    conn,
                    _audit_event(
                        "connector_record_blocked",
                        source_path,
                        "blocked",
                        "; ".join(f"{finding.rule_id}: {finding.message}" for finding in safety.findings),
                        now,
                    ),
                )
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
                    "deleted_or_archived": record.deleted_or_archived,
                },
            )
            if not inserted:
                continue

            changed += 1
            if record.deleted_or_archived:
                archived += 1
                delete_document(conn, _source_id(record.external_id))
                insert_audit_event(
                    conn,
                    _audit_event(
                        "connector_record_archived",
                        source_path,
                        "archived",
                        f"Recorded archived Confluence page {record.external_id}.",
                        now,
                    ),
                )
                continue

            normalized = connector.normalize(record)
            normalized_raw = json.dumps(normalized, sort_keys=True)
            normalized_safety = check_content_safety(normalized_raw)
            if not normalized_safety.allowed:
                blocked += 1
                insert_audit_event(
                    conn,
                    _audit_event("connector_record_blocked", source_path, "blocked", "Normalized content failed safety gate.", now),
                )
                continue

            document = _document_from_payload(normalized, source_path or record.external_id, normalized_raw, now)
            replace_document(conn, document)
            for index, chunk_text in enumerate(_chunk_text(str(normalized["content"]))):
                insert_chunk(conn, _chunk_from_document(document, chunk_text, index))
            indexed += 1
            insert_audit_event(
                conn,
                _audit_event(
                    "connector_document_indexed",
                    source_path,
                    "indexed",
                    f"Indexed Confluence page {record.external_id} version {record.external_version}.",
                    now,
                ),
            )

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
    except Exception as exc:
        conn.rollback()
        upsert_sync_state(
            conn,
            {
                "connection_id": connector.connection_id,
                "sync_cursor": None,
                "last_successful_sync_at": None,
                "last_attempted_sync_at": now,
                "last_status": "error",
                "last_error": str(exc),
                "records_seen": fetched.records_seen,
                "records_changed": changed,
            },
        )
        conn.commit()
        raise
    finally:
        conn.close()

    return SyncResult(
        connector.connection_id,
        connector.source_type,
        connector.mode,
        False,
        fetched.records_seen,
        changed,
        indexed,
        archived,
        blocked,
        "success",
        "Synced Confluence fixture records to SQLite.",
    )


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = data.strip()
        if value:
            self.parts.append(value)


def _body_text(payload: dict[str, Any]) -> str:
    body = payload.get("body") if isinstance(payload.get("body"), dict) else {}
    storage = body.get("storage") if isinstance(body.get("storage"), dict) else {}
    value = storage.get("value")
    if not isinstance(value, str):
        return ""
    parser = _HTMLTextExtractor()
    parser.feed(value)
    return re.sub(r"\s+", " ", html.unescape(" ".join(parser.parts))).strip()


def _labels(payload: dict[str, Any]) -> list[str]:
    raw_labels = payload.get("labels", [])
    if not isinstance(raw_labels, list):
        return []
    labels: list[str] = []
    for label in raw_labels:
        if isinstance(label, str):
            labels.append(label)
        elif isinstance(label, dict) and label.get("name"):
            labels.append(str(label["name"]))
    return labels


def _metadata_value(labels: list[str], prefix: str) -> str | None:
    marker = f"{prefix}:"
    for label in labels:
        if label.startswith(marker):
            return label.removeprefix(marker)
    return None


def _join_url(base: Any, webui: Any) -> str | None:
    if not isinstance(webui, str):
        return None
    if isinstance(base, str) and base:
        return f"{base.rstrip('/')}/{webui.lstrip('/')}"
    return webui


def _source_id(external_id: str) -> str:
    return f"confluence:{external_id}"


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
