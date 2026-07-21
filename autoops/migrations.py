from __future__ import annotations

import sqlite3


CURRENT_SCHEMA_VERSION = 3


MIGRATIONS: tuple[tuple[int, str], ...] = (
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """,
    ),
    (
        2,
        """
        CREATE TABLE IF NOT EXISTS source_connections (
            connection_id TEXT PRIMARY KEY,
            source_type TEXT NOT NULL,
            display_name TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            base_url TEXT,
            scope_description TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS sync_state (
            connection_id TEXT PRIMARY KEY REFERENCES source_connections(connection_id) ON DELETE CASCADE,
            sync_cursor TEXT,
            last_successful_sync_at TEXT,
            last_attempted_sync_at TEXT,
            last_status TEXT NOT NULL DEFAULT 'never_run',
            last_error TEXT,
            records_seen INTEGER NOT NULL DEFAULT 0,
            records_changed INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS raw_source_records (
            raw_id TEXT PRIMARY KEY,
            connection_id TEXT NOT NULL REFERENCES source_connections(connection_id) ON DELETE CASCADE,
            source_type TEXT NOT NULL,
            external_id TEXT NOT NULL,
            external_url TEXT,
            external_version TEXT,
            external_created_at TEXT,
            external_updated_at TEXT,
            payload_hash TEXT,
            sanitized_payload_json TEXT,
            payload_storage_mode TEXT NOT NULL DEFAULT 'hash_only',
            ingested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_or_archived INTEGER NOT NULL DEFAULT 0,
            UNIQUE(connection_id, source_type, external_id, external_version)
        );

        CREATE TABLE IF NOT EXISTS source_relationships (
            relationship_id TEXT PRIMARY KEY,
            from_source_id TEXT NOT NULL,
            to_source_id TEXT NOT NULL,
            relationship_type TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(from_source_id, to_source_id, relationship_type)
        );

        CREATE INDEX IF NOT EXISTS idx_raw_source_records_external
            ON raw_source_records(connection_id, source_type, external_id);

        CREATE INDEX IF NOT EXISTS idx_raw_source_records_updated
            ON raw_source_records(source_type, external_updated_at);

        CREATE INDEX IF NOT EXISTS idx_source_relationships_from
            ON source_relationships(from_source_id);

        CREATE INDEX IF NOT EXISTS idx_source_relationships_to
            ON source_relationships(to_source_id);
        """,
    ),
    (
        3,
        """
        CREATE TABLE IF NOT EXISTS chunk_embeddings (
            chunk_id TEXT PRIMARY KEY REFERENCES chunks(chunk_id) ON DELETE CASCADE,
            embedding_model TEXT NOT NULL,
            dimensions INTEGER NOT NULL,
            embedding_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_model
            ON chunk_embeddings(embedding_model);
        """,
    ),
)


def migrate(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON")
    _ensure_schema_version_table(conn)
    applied_versions = {
        row["version"] if isinstance(row, sqlite3.Row) else row[0]
        for row in conn.execute("SELECT version FROM schema_version")
    }

    for version, sql in MIGRATIONS:
        if version in applied_versions:
            continue
        conn.executescript(sql)
        conn.execute("INSERT OR IGNORE INTO schema_version(version) VALUES (?)", (version,))

    conn.commit()


def get_schema_version(conn: sqlite3.Connection) -> int:
    _ensure_schema_version_table(conn)
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    if row is None or row[0] is None:
        return 0
    return int(row[0])


def _ensure_schema_version_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
