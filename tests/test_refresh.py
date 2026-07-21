import tempfile
import unittest
from pathlib import Path

from autoops.refresh import ConnectorLock, format_refresh_summary, refresh_connections
from autoops.storage import connect, initialize, list_sync_states


class RefreshTests(unittest.TestCase):
    def test_manual_refresh_all_runs_confluence_fixture_connector(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "autoops.db"
            lock_dir = Path(tmpdir) / "locks"

            summary = refresh_connections(db_path, connection="all", trigger="manual", lock_dir=lock_dir)

            self.assertEqual("success", summary.status)
            self.assertEqual(["confluence", "gitlab", "jira"], summary.requested_connections)
            self.assertEqual("manual", summary.trigger)
            self.assertEqual("success", summary.items[0].status)
            self.assertFalse(summary.items[0].locked)
            self.assertEqual(4, summary.items[0].result["records_seen"])
            self.assertEqual("success", summary.items[1].status)
            self.assertEqual(1, summary.items[1].result["records_seen"])
            self.assertEqual("success", summary.items[2].status)
            self.assertEqual(3, summary.items[2].result["records_seen"])
            self.assertFalse((lock_dir / "confluence.lock").exists())
            self.assertFalse((lock_dir / "gitlab.lock").exists())
            self.assertFalse((lock_dir / "jira.lock").exists())

    def test_scheduled_refresh_is_cron_compatible_and_records_trigger(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = refresh_connections(
                Path(tmpdir) / "autoops.db",
                connection="confluence",
                trigger="scheduled",
                lock_dir=Path(tmpdir) / "locks",
            )

            formatted = format_refresh_summary(summary)

            self.assertEqual("scheduled", summary.trigger)
            self.assertIn("Trigger: scheduled", formatted)
            self.assertIn("confluence: success", formatted)

    def test_refresh_skips_locked_connection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_dir = Path(tmpdir) / "locks"
            lock_path = lock_dir / "confluence.lock"

            with ConnectorLock(lock_path) as lock:
                self.assertTrue(lock.acquired)
                summary = refresh_connections(
                    Path(tmpdir) / "autoops.db",
                    connection="confluence",
                    lock_dir=lock_dir,
                )

            self.assertEqual("partial", summary.status)
            self.assertEqual("locked", summary.items[0].status)
            self.assertTrue(summary.items[0].locked)
            self.assertIsNone(summary.items[0].result)
            self.assertFalse(lock_path.exists())

    def test_sync_status_lists_latest_refresh_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "autoops.db"
            refresh_connections(db_path, connection="confluence", lock_dir=Path(tmpdir) / "locks")

            conn = connect(db_path)
            try:
                initialize(conn)
                states = list_sync_states(conn)
            finally:
                conn.close()

            self.assertEqual(1, len(states))
            self.assertEqual("confluence-fixture", states[0]["connection_id"])
            self.assertEqual("success", states[0]["last_status"])
            self.assertEqual(4, states[0]["records_seen"])

    def test_refresh_all_sync_status_lists_all_fixture_connections(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "autoops.db"
            refresh_connections(db_path, connection="all", lock_dir=Path(tmpdir) / "locks")

            conn = connect(db_path)
            try:
                initialize(conn)
                states = list_sync_states(conn)
            finally:
                conn.close()

            self.assertEqual(["confluence-fixture", "gitlab-fixture", "jira-fixture"], [state["connection_id"] for state in states])

    def test_invalid_connection_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(ValueError):
                refresh_connections(Path(tmpdir) / "autoops.db", connection="slack")


if __name__ == "__main__":
    unittest.main()
