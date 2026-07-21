from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from .embeddings import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL, embed_text, serialize_embedding
from .migrations import get_schema_version, migrate


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS documents (
    source_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_url TEXT,
    title TEXT NOT NULL,
    service TEXT,
    component TEXT,
    alert_name TEXT,
    ticket_id TEXT,
    incident_id TEXT,
    thread_id TEXT,
    channel TEXT,
    owner_team TEXT,
    owner_contact TEXT,
    author TEXT,
    created_at TEXT,
    updated_at TEXT,
    version TEXT,
    deprecated INTEGER NOT NULL DEFAULT 0,
    tags TEXT NOT NULL DEFAULT '[]',
    content_hash TEXT NOT NULL,
    ingested_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES documents(source_id) ON DELETE CASCADE,
    chunk_text TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    source_path TEXT NOT NULL,
    title TEXT NOT NULL,
    source_type TEXT NOT NULL,
    service TEXT,
    component TEXT,
    alert_name TEXT,
    updated_at TEXT,
    version TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    chunk_id UNINDEXED,
    source_id UNINDEXED,
    title,
    chunk_text,
    service,
    component,
    alert_name,
    source_type
);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    source_path TEXT,
    status TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunk_embeddings (
    chunk_id TEXT PRIMARY KEY REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    embedding_model TEXT NOT NULL,
    dimensions INTEGER NOT NULL,
    embedding_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    migrate(conn)
    conn.commit()


def current_schema_version(conn: sqlite3.Connection) -> int:
    return get_schema_version(conn)


def clear_index(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM chunk_embeddings")
    conn.execute("DELETE FROM chunks_fts")
    conn.execute("DELETE FROM chunks")
    conn.execute("DELETE FROM documents")
    conn.execute("DELETE FROM audit_events")
    conn.commit()


def upsert_source_connection(conn: sqlite3.Connection, connection: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO source_connections (
            connection_id, source_type, display_name, enabled, base_url, scope_description
        ) VALUES (
            :connection_id, :source_type, :display_name, :enabled, :base_url, :scope_description
        )
        ON CONFLICT(connection_id) DO UPDATE SET
            source_type = excluded.source_type,
            display_name = excluded.display_name,
            enabled = excluded.enabled,
            base_url = excluded.base_url,
            scope_description = excluded.scope_description,
            updated_at = CURRENT_TIMESTAMP
        """,
        {
            **connection,
            "enabled": 1 if connection.get("enabled", True) else 0,
        },
    )


def record_raw_source_record(conn: sqlite3.Connection, record: dict[str, Any]) -> bool:
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO raw_source_records (
            raw_id, connection_id, source_type, external_id, external_url,
            external_version, external_created_at, external_updated_at, payload_hash,
            sanitized_payload_json, payload_storage_mode, deleted_or_archived
        ) VALUES (
            :raw_id, :connection_id, :source_type, :external_id, :external_url,
            :external_version, :external_created_at, :external_updated_at, :payload_hash,
            :sanitized_payload_json, :payload_storage_mode, :deleted_or_archived
        )
        """,
        {
            **record,
            "raw_id": record.get("raw_id") or str(uuid.uuid4()),
            "payload_storage_mode": record.get("payload_storage_mode", "hash_only"),
            "sanitized_payload_json": record.get("sanitized_payload_json"),
            "deleted_or_archived": 1 if record.get("deleted_or_archived") else 0,
        },
    )
    return cursor.rowcount == 1


def upsert_sync_state(conn: sqlite3.Connection, state: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO sync_state (
            connection_id, sync_cursor, last_successful_sync_at, last_attempted_sync_at,
            last_status, last_error, records_seen, records_changed
        ) VALUES (
            :connection_id, :sync_cursor, :last_successful_sync_at, :last_attempted_sync_at,
            :last_status, :last_error, :records_seen, :records_changed
        )
        ON CONFLICT(connection_id) DO UPDATE SET
            sync_cursor = excluded.sync_cursor,
            last_successful_sync_at = excluded.last_successful_sync_at,
            last_attempted_sync_at = excluded.last_attempted_sync_at,
            last_status = excluded.last_status,
            last_error = excluded.last_error,
            records_seen = excluded.records_seen,
            records_changed = excluded.records_changed
        """,
        state,
    )


def list_sync_states(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            sc.connection_id,
            sc.source_type,
            sc.display_name,
            sc.enabled,
            sc.base_url,
            sc.scope_description,
            ss.sync_cursor,
            ss.last_successful_sync_at,
            ss.last_attempted_sync_at,
            ss.last_status,
            ss.last_error,
            ss.records_seen,
            ss.records_changed
        FROM source_connections sc
        LEFT JOIN sync_state ss ON ss.connection_id = sc.connection_id
        ORDER BY sc.connection_id ASC
        """
    ).fetchall()
    return [
        {
            **dict(row),
            "enabled": bool(row["enabled"]),
            "last_status": row["last_status"] or "never_run",
            "records_seen": row["records_seen"] or 0,
            "records_changed": row["records_changed"] or 0,
        }
        for row in rows
    ]


def replace_document(conn: sqlite3.Connection, document: dict[str, Any]) -> None:
    chunk_ids = _chunk_ids_for_source(conn, document["source_id"])
    if chunk_ids:
        conn.executemany("DELETE FROM chunk_embeddings WHERE chunk_id = ?", [(chunk_id,) for chunk_id in chunk_ids])
    conn.execute("DELETE FROM chunks_fts WHERE source_id = ?", (document["source_id"],))
    conn.execute("DELETE FROM chunks WHERE source_id = ?", (document["source_id"],))
    conn.execute("DELETE FROM documents WHERE source_id = ?", (document["source_id"],))
    insert_document(conn, document)


def delete_document(conn: sqlite3.Connection, source_id: str) -> None:
    chunk_ids = _chunk_ids_for_source(conn, source_id)
    if chunk_ids:
        conn.executemany("DELETE FROM chunk_embeddings WHERE chunk_id = ?", [(chunk_id,) for chunk_id in chunk_ids])
    conn.execute("DELETE FROM chunks_fts WHERE source_id = ?", (source_id,))
    conn.execute("DELETE FROM chunks WHERE source_id = ?", (source_id,))
    conn.execute("DELETE FROM documents WHERE source_id = ?", (source_id,))


def insert_document(conn: sqlite3.Connection, document: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO documents (
            source_id, source_type, source_path, source_url, title, service,
            component, alert_name, ticket_id, incident_id, thread_id, channel,
            owner_team, owner_contact, author, created_at, updated_at, version,
            deprecated, tags, content_hash, ingested_at
        ) VALUES (
            :source_id, :source_type, :source_path, :source_url, :title, :service,
            :component, :alert_name, :ticket_id, :incident_id, :thread_id, :channel,
            :owner_team, :owner_contact, :author, :created_at, :updated_at, :version,
            :deprecated, :tags, :content_hash, :ingested_at
        )
        """,
        {
            **document,
            "deprecated": 1 if document.get("deprecated") else 0,
            "tags": json.dumps(document.get("tags", []), sort_keys=True),
        },
    )


def insert_chunk(conn: sqlite3.Connection, chunk: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO chunks (
            chunk_id, source_id, chunk_text, chunk_index, source_path, title,
            source_type, service, component, alert_name, updated_at, version
        ) VALUES (
            :chunk_id, :source_id, :chunk_text, :chunk_index, :source_path, :title,
            :source_type, :service, :component, :alert_name, :updated_at, :version
        )
        """,
        chunk,
    )
    conn.execute(
        """
        INSERT INTO chunks_fts (
            chunk_id, source_id, title, chunk_text, service, component, alert_name, source_type
        ) VALUES (
            :chunk_id, :source_id, :title, :chunk_text, :service, :component, :alert_name, :source_type
        )
        """,
        chunk,
    )
    upsert_chunk_embedding(conn, chunk["chunk_id"], _embedding_text(chunk))


def upsert_chunk_embedding(conn: sqlite3.Connection, chunk_id: str, text: str) -> None:
    vector = embed_text(text)
    conn.execute(
        """
        INSERT INTO chunk_embeddings (
            chunk_id, embedding_model, dimensions, embedding_json
        ) VALUES (
            ?, ?, ?, ?
        )
        ON CONFLICT(chunk_id) DO UPDATE SET
            embedding_model = excluded.embedding_model,
            dimensions = excluded.dimensions,
            embedding_json = excluded.embedding_json
        """,
        (chunk_id, EMBEDDING_MODEL, EMBEDDING_DIMENSIONS, serialize_embedding(vector)),
    )


def insert_audit_event(conn: sqlite3.Connection, event: dict[str, str | None]) -> None:
    conn.execute(
        """
        INSERT INTO audit_events (
            event_id, event_type, source_path, status, message, created_at
        ) VALUES (
            :event_id, :event_type, :source_path, :status, :message, :created_at
        )
        """,
        event,
    )


def list_sources(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            source_id, source_type, source_path, source_url, title, service,
            component, alert_name, ticket_id, incident_id, thread_id, channel,
            owner_team, owner_contact, author, created_at, updated_at, version,
            deprecated, tags, content_hash, ingested_at
        FROM documents
        ORDER BY updated_at DESC, source_id ASC
        """
    ).fetchall()
    return [_document_row_to_dict(row) for row in rows]


def get_source(conn: sqlite3.Connection, source_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT
            source_id, source_type, source_path, source_url, title, service,
            component, alert_name, ticket_id, incident_id, thread_id, channel,
            owner_team, owner_contact, author, created_at, updated_at, version,
            deprecated, tags, content_hash, ingested_at
        FROM documents
        WHERE source_id = ?
        """,
        (source_id,),
    ).fetchone()
    if row is None:
        return None

    document = _document_row_to_dict(row)
    chunks = conn.execute(
        """
        SELECT chunk_id, chunk_text, chunk_index
        FROM chunks
        WHERE source_id = ?
        ORDER BY chunk_index ASC
        """,
        (source_id,),
    ).fetchall()
    document["chunks"] = [dict(chunk) for chunk in chunks]
    return document


def _document_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    document = dict(row)
    document["deprecated"] = bool(document["deprecated"])
    try:
        document["tags"] = json.loads(document["tags"])
    except json.JSONDecodeError:
        document["tags"] = []
    return document


def _chunk_ids_for_source(conn: sqlite3.Connection, source_id: str) -> list[str]:
    rows = conn.execute("SELECT chunk_id FROM chunks WHERE source_id = ?", (source_id,)).fetchall()
    return [row["chunk_id"] for row in rows]


def _embedding_text(chunk: dict[str, Any]) -> str:
    metadata = " ".join(
        str(chunk.get(field) or "")
        for field in ("title", "source_type", "service", "component", "alert_name")
    )
    return f"{metadata} {chunk['chunk_text']}"
