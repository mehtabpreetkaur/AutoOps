import sqlite3
import tempfile
import unittest
from pathlib import Path

from autoops.ingest import ingest_path


class IngestionTests(unittest.TestCase):
    def test_ingests_mock_data_into_sqlite_and_fts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "autoops.db"
            expected_documents = len(list(Path("mock_data").rglob("*.json")))

            summary = ingest_path(Path("mock_data"), db_path, rebuild=True)

            self.assertEqual(expected_documents, summary.documents_seen)
            self.assertEqual(expected_documents, summary.documents_indexed)
            self.assertEqual(0, summary.documents_blocked)
            self.assertGreaterEqual(summary.chunks_indexed, expected_documents)

            conn = sqlite3.connect(db_path)
            try:
                self.assertEqual(expected_documents, conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0])
                self.assertGreaterEqual(conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0], expected_documents)
                self.assertGreaterEqual(
                    conn.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0],
                    expected_documents,
                )
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
                    conn.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()[0],
                )
                self.assertEqual(expected_documents, conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0])
                self.assertGreaterEqual(
                    conn.execute("SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH 'kafka'").fetchone()[0],
                    5,
                )
                checkout_chunks = conn.execute(
                    "SELECT COUNT(*) FROM chunks WHERE source_id = 'mock-conf-003'"
                ).fetchone()[0]
                self.assertGreaterEqual(checkout_chunks, 2)
            finally:
                conn.close()

    def test_blocks_source_with_external_email_before_indexing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "mock_data"
            root.mkdir()
            db_path = Path(tmpdir) / "autoops.db"
            (root / "bad.json").write_text(
                """
                {
                  "source_type": "jira",
                  "source_id": "bad-001",
                  "title": "Unsafe customer contact",
                  "updated_at": "2026-07-01T00:00:00Z",
                  "content": "Customer email is customer@example.com"
                }
                """,
                encoding="utf-8",
            )

            summary = ingest_path(root, db_path, rebuild=True)

            self.assertEqual(1, summary.documents_seen)
            self.assertEqual(0, summary.documents_indexed)
            self.assertEqual(1, summary.documents_blocked)

            conn = sqlite3.connect(db_path)
            try:
                self.assertEqual(0, conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0])
                event = conn.execute("SELECT status, message FROM audit_events").fetchone()
                self.assertEqual("blocked", event[0])
                self.assertIn("customer_or_external_email", event[1])
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
