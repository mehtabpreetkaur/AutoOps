from __future__ import annotations

import hashlib
import json
import textwrap
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .safety import check_content_safety
from .storage import clear_index, connect, initialize, insert_audit_event, insert_chunk, insert_document


REQUIRED_FIELDS = ("source_type", "source_id", "title", "updated_at", "content")
DEFAULT_CHUNK_SIZE = 900
DEFAULT_CHUNK_OVERLAP = 120


@dataclass(frozen=True)
class IngestionSummary:
    documents_seen: int
    documents_indexed: int
    documents_blocked: int
    chunks_indexed: int
    db_path: Path


def ingest_path(source_root: Path, db_path: Path, rebuild: bool = False) -> IngestionSummary:
    source_root = source_root.resolve()
    db_path = db_path.resolve()
    json_files = sorted(source_root.rglob("*.json"))

    conn = connect(db_path)
    try:
        initialize(conn)
        if rebuild:
            clear_index(conn)

        indexed = 0
        blocked = 0
        chunk_count = 0

        for path in json_files:
            now = _now()
            rel_path = str(path.relative_to(Path.cwd())) if path.is_relative_to(Path.cwd()) else str(path)
            try:
                raw = path.read_text(encoding="utf-8")
                payload = json.loads(raw)
                _validate_payload(payload)
                safety = check_content_safety(raw)
                if not safety.allowed:
                    blocked += 1
                    messages = "; ".join(f"{f.rule_id}: {f.message}" for f in safety.findings)
                    insert_audit_event(
                        conn,
                        _audit_event("ingest_blocked", rel_path, "blocked", messages, now),
                    )
                    continue

                document = _document_from_payload(payload, rel_path, raw, now)
                insert_document(conn, document)
                chunks = _chunk_text(str(payload["content"]))
                for index, chunk_text in enumerate(chunks):
                    chunk = _chunk_from_document(document, chunk_text, index)
                    insert_chunk(conn, chunk)
                    chunk_count += 1

                indexed += 1
                insert_audit_event(
                    conn,
                    _audit_event(
                        "ingest_document",
                        rel_path,
                        "indexed",
                        f"Indexed {len(chunks)} chunk(s) for {payload['source_id']}.",
                        now,
                    ),
                )
            except Exception as exc:
                blocked += 1
                insert_audit_event(
                    conn,
                    _audit_event("ingest_error", rel_path, "error", str(exc), now),
                )

        conn.commit()
        return IngestionSummary(
            documents_seen=len(json_files),
            documents_indexed=indexed,
            documents_blocked=blocked,
            chunks_indexed=chunk_count,
            db_path=db_path,
        )
    finally:
        conn.close()


def _validate_payload(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise ValueError("Source JSON must be an object.")
    missing = [field for field in REQUIRED_FIELDS if field not in payload or payload[field] in (None, "")]
    if missing:
        raise ValueError(f"Missing required field(s): {', '.join(missing)}")


def _document_from_payload(payload: dict[str, Any], source_path: str, raw: str, ingested_at: str) -> dict[str, Any]:
    return {
        "source_id": str(payload["source_id"]),
        "source_type": str(payload["source_type"]),
        "source_path": source_path,
        "source_url": _optional_str(payload.get("source_url")),
        "title": str(payload["title"]),
        "service": _optional_str(payload.get("service")),
        "component": _optional_str(payload.get("component")),
        "alert_name": _optional_str(payload.get("alert_name")),
        "ticket_id": _optional_str(payload.get("ticket_id")),
        "incident_id": _optional_str(payload.get("incident_id")),
        "thread_id": _optional_str(payload.get("thread_id")),
        "channel": _optional_str(payload.get("channel")),
        "owner_team": _optional_str(payload.get("owner_team")),
        "owner_contact": _optional_str(payload.get("owner_contact")),
        "author": _optional_str(payload.get("author")),
        "created_at": _optional_str(payload.get("created_at")),
        "updated_at": str(payload["updated_at"]),
        "version": _optional_str(payload.get("version")),
        "deprecated": bool(payload.get("deprecated", False)),
        "tags": payload.get("tags", []),
        "content_hash": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "ingested_at": ingested_at,
    }


def _chunk_from_document(document: dict[str, Any], chunk_text: str, index: int) -> dict[str, Any]:
    return {
        "chunk_id": f"{document['source_id']}:{index}",
        "source_id": document["source_id"],
        "chunk_text": chunk_text,
        "chunk_index": index,
        "source_path": document["source_path"],
        "title": document["title"],
        "source_type": document["source_type"],
        "service": document["service"],
        "component": document["component"],
        "alert_name": document["alert_name"],
        "updated_at": document["updated_at"],
        "version": document["version"],
    }


def _chunk_text(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_CHUNK_OVERLAP) -> list[str]:
    normalized = " ".join(textwrap.dedent(text).strip().split())
    if not normalized:
        return []
    if len(normalized) <= chunk_size:
        return [normalized]

    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + chunk_size, len(normalized))
        chunks.append(normalized[start:end].strip())
        if end == len(normalized):
            break
        start = max(end - overlap, start + 1)
    return chunks


def _audit_event(
    event_type: str,
    source_path: str | None,
    status: str,
    message: str,
    created_at: str,
) -> dict[str, str | None]:
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "source_path": source_path,
        "status": status,
        "message": message,
        "created_at": created_at,
    }


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
