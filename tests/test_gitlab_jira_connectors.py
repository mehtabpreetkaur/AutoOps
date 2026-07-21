import sqlite3
import tempfile
import unittest
from pathlib import Path

from autoops.connectors import (
    GitLabFixtureConnector,
    JiraFixtureConnector,
    sync_gitlab_fixture,
    sync_jira_fixture,
)
from autoops.query import query_knowledge_hub


class GitLabJiraConnectorTests(unittest.TestCase):
    def test_gitlab_live_mode_fails_closed_until_account_setup_is_approved(self) -> None:
        result = GitLabFixtureConnector(live=True).validate_connection()

        self.assertFalse(result.ok)
        self.assertEqual("live", result.mode)
        self.assertIn("Live GitLab mode is not implemented", result.message)

    def test_jira_live_mode_fails_closed_until_account_setup_is_approved(self) -> None:
        result = JiraFixtureConnector(live=True).validate_connection()

        self.assertFalse(result.ok)
        self.assertEqual("live", result.mode)
        self.assertIn("Live Jira mode is not implemented", result.message)

    def test_gitlab_fixture_sync_decodes_base64_and_indexes_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "autoops.db"

            result = sync_gitlab_fixture(db_path)

            self.assertEqual("success", result.status)
            self.assertEqual(1, result.records_seen)
            self.assertEqual(1, result.documents_indexed)

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                doc = conn.execute(
                    """
                    SELECT source_id, source_type, title, service, version
                    FROM documents
                    WHERE source_id = 'gitlab:runbooks/payments/kafka-consumer-lag.md'
                    """
                ).fetchone()
                self.assertEqual("gitlab", doc["source_type"])
                self.assertEqual("payments", doc["service"])
                self.assertEqual("fixture-commit-001", doc["version"])

                chunk = conn.execute(
                    """
                    SELECT chunk_text FROM chunks
                    WHERE source_id = 'gitlab:runbooks/payments/kafka-consumer-lag.md'
                    """
                ).fetchone()
                self.assertIn("Check broker health before restarting consumer pods.", chunk["chunk_text"])
            finally:
                conn.close()

    def test_jira_fixture_sync_indexes_incident_access_request_and_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "autoops.db"

            result = sync_jira_fixture(db_path)

            self.assertEqual("success", result.status)
            self.assertEqual(3, result.records_seen)
            self.assertEqual(3, result.documents_indexed)

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    """
                    SELECT source_id, ticket_id, title, component
                    FROM documents
                    WHERE source_type = 'jira'
                    ORDER BY source_id
                    """
                ).fetchall()
                self.assertEqual(["jira:CHG-7001", "jira:INC-3001", "jira:OPS-5001"], [row["source_id"] for row in rows])
                self.assertIn("Production change", rows[0]["title"])
                self.assertEqual("INC-3001", rows[1]["ticket_id"])
                self.assertEqual("payments-kafka-consumer", rows[1]["component"])
            finally:
                conn.close()

    def test_query_can_use_gitlab_and_jira_fixture_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "autoops.db"
            sync_gitlab_fixture(db_path)
            sync_jira_fixture(db_path)

            gitlab_result = query_knowledge_hub("broker health restarting consumer pods", db_path)
            jira_result = query_knowledge_hub("access request payments runbook space", db_path)

            self.assertEqual("gitlab:runbooks/payments/kafka-consumer-lag.md", gitlab_result.sources[0]["source_id"])
            self.assertEqual("jira:OPS-5001", jira_result.sources[0]["source_id"])


if __name__ == "__main__":
    unittest.main()
