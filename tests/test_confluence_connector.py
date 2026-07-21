import sqlite3
import tempfile
import unittest
from pathlib import Path

from autoops.connectors import ConfluenceFixtureConnector, sync_confluence_fixture
from autoops.query import query_knowledge_hub


class ConfluenceConnectorTests(unittest.TestCase):
    def test_live_mode_fails_closed_until_account_setup_is_approved(self) -> None:
        connector = ConfluenceFixtureConnector(live=True)

        result = connector.validate_connection()

        self.assertFalse(result.ok)
        self.assertEqual("live", result.mode)
        self.assertIn("Live Confluence mode is not implemented", result.message)

    def test_dry_run_validates_fixtures_without_creating_database(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "autoops.db"

            result = sync_confluence_fixture(db_path, dry_run=True)

            self.assertEqual("dry_run", result.status)
            self.assertTrue(result.dry_run)
            self.assertEqual(4, result.records_seen)
            self.assertEqual(0, result.records_blocked)
            self.assertFalse(db_path.exists())

    def test_fixture_sync_indexes_latest_current_confluence_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "autoops.db"

            result = sync_confluence_fixture(db_path)

            self.assertEqual("success", result.status)
            self.assertEqual(4, result.records_seen)
            self.assertEqual(4, result.records_changed)
            self.assertEqual(3, result.documents_indexed)
            self.assertEqual(1, result.records_archived)

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                doc = conn.execute(
                    """
                    SELECT source_id, title, version, updated_at, source_url
                    FROM documents
                    WHERE source_id = 'confluence:conf-page-1001'
                    """
                ).fetchone()
                self.assertIsNotNone(doc)
                self.assertEqual("4", doc["version"])
                self.assertEqual("2026-07-21T08:00:00Z", doc["updated_at"])
                self.assertEqual(
                    "mock://confluence/spaces/AUTOOPS/pages/conf-page-1001",
                    doc["source_url"],
                )

                raw = conn.execute(
                    """
                    SELECT COUNT(*), SUM(CASE WHEN sanitized_payload_json IS NULL THEN 1 ELSE 0 END)
                    FROM raw_source_records
                    WHERE connection_id = 'confluence-fixture'
                    """
                ).fetchone()
                self.assertEqual(4, raw[0])
                self.assertEqual(4, raw[1])

                state = conn.execute(
                    """
                    SELECT last_status, records_seen, records_changed, sync_cursor
                    FROM sync_state
                    WHERE connection_id = 'confluence-fixture'
                    """
                ).fetchone()
                self.assertEqual("success", state["last_status"])
                self.assertEqual(4, state["records_seen"])
                self.assertEqual(4, state["records_changed"])
                self.assertEqual("2026-07-21T08:00:00Z", state["sync_cursor"])
            finally:
                conn.close()

    def test_fixture_sync_is_idempotent_for_existing_raw_versions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "autoops.db"

            first = sync_confluence_fixture(db_path)
            second = sync_confluence_fixture(db_path)

            self.assertEqual(4, first.records_changed)
            self.assertEqual(0, second.records_changed)
            self.assertEqual(0, second.documents_indexed)

    def test_query_can_use_synced_confluence_fixture_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "autoops.db"
            sync_confluence_fixture(db_path)

            result = query_knowledge_hub("Kafka consumer lag settlement replay restart", db_path)

            self.assertGreaterEqual(len(result.sources), 1)
            self.assertEqual("confluence:conf-page-1001", result.sources[0]["source_id"])
            self.assertIn("monitor lag slope for 15 minutes", result.sources[0]["excerpt"])


if __name__ == "__main__":
    unittest.main()
