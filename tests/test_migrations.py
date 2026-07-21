import sqlite3
import tempfile
import unittest
from pathlib import Path

from autoops.ingest import ingest_path
from autoops.migrations import CURRENT_SCHEMA_VERSION
from autoops.storage import connect, current_schema_version, initialize


EXPECTED_PHASE_2_TABLES = {
    "schema_version",
    "source_connections",
    "sync_state",
    "raw_source_records",
    "source_relationships",
    "chunk_embeddings",
}


class MigrationTests(unittest.TestCase):
    def test_fresh_database_gets_phase_2_tables_and_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            conn = connect(Path(tmpdir) / "autoops.db")
            try:
                initialize(conn)

                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
                self.assertTrue(EXPECTED_PHASE_2_TABLES.issubset(tables))
                self.assertEqual(CURRENT_SCHEMA_VERSION, current_schema_version(conn))
            finally:
                conn.close()

    def test_phase_1_database_migrates_without_losing_documents(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "autoops.db"
            summary = ingest_path(Path("mock_data"), db_path, rebuild=True)

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                initialize(conn)

                self.assertEqual(summary.documents_indexed, conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0])
                self.assertEqual(CURRENT_SCHEMA_VERSION, current_schema_version(conn))
                self.assertEqual(1, conn.execute("SELECT COUNT(*) FROM schema_version WHERE version = 2").fetchone()[0])
                self.assertEqual(1, conn.execute("SELECT COUNT(*) FROM schema_version WHERE version = 3").fetchone()[0])
            finally:
                conn.close()

    def test_raw_source_record_default_blocks_payload_storage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            conn = connect(Path(tmpdir) / "autoops.db")
            try:
                initialize(conn)
                conn.execute(
                    """
                    INSERT INTO source_connections (
                        connection_id, source_type, display_name
                    ) VALUES ('confluence-test', 'confluence', 'Confluence Test')
                    """
                )
                conn.execute(
                    """
                    INSERT INTO raw_source_records (
                        raw_id, connection_id, source_type, external_id, external_version, payload_hash
                    ) VALUES (
                        'raw-1', 'confluence-test', 'confluence', 'page-1', 'v1', 'hash-1'
                    )
                    """
                )
                row = conn.execute(
                    """
                    SELECT payload_storage_mode, sanitized_payload_json
                    FROM raw_source_records
                    WHERE raw_id = 'raw-1'
                    """
                ).fetchone()

                self.assertEqual("hash_only", row["payload_storage_mode"])
                self.assertIsNone(row["sanitized_payload_json"])
            finally:
                conn.close()

    def test_raw_source_record_uniqueness_prevents_duplicate_external_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            conn = connect(Path(tmpdir) / "autoops.db")
            try:
                initialize(conn)
                conn.execute(
                    """
                    INSERT INTO source_connections (
                        connection_id, source_type, display_name
                    ) VALUES ('confluence-test', 'confluence', 'Confluence Test')
                    """
                )
                insert_sql = """
                    INSERT INTO raw_source_records (
                        raw_id, connection_id, source_type, external_id, external_version, payload_hash
                    ) VALUES (?, 'confluence-test', 'confluence', 'page-1', 'v1', ?)
                """
                conn.execute(insert_sql, ("raw-1", "hash-1"))

                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(insert_sql, ("raw-2", "hash-2"))
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
