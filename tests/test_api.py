import tempfile
import unittest
from pathlib import Path

from autoops.api import QueryRequest, RefreshRequest, SyncRequest, create_app
from autoops.ingest import ingest_path


class APITests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "autoops.db"
        ingest_path(Path("mock_data"), self.db_path, rebuild=True)
        self.app = create_app(self.db_path)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_health(self) -> None:
        response = self._endpoint("/health")()

        self.assertEqual("ok", response["status"])

    def test_query_endpoint_returns_contradictions(self) -> None:
        response = self._endpoint("/query")(
            QueryRequest(query="What should I do for HighKafkaConsumerLag in payments?")
        )

        self.assertEqual("mock-conf-001", response["sources"][0]["source_id"])
        self.assertGreaterEqual(len(response["contradictions"]), 1)

    def test_sources_and_source_detail(self) -> None:
        sources_response = self._endpoint("/sources")()
        detail_response = self._endpoint("/sources/{source_id}")("mock-conf-001")
        expected_documents = len(list(Path("mock_data").rglob("*.json")))

        self.assertEqual(expected_documents, len(sources_response["sources"]))
        self.assertEqual("Kafka Consumer Lag Runbook", detail_response["title"])

    def test_query_endpoint_supports_non_kafka_scenario(self) -> None:
        response = self._endpoint("/query")(
            QueryRequest(query="DatabaseConnectionPoolSaturation in orders-api")
        )

        self.assertEqual("mock-conf-002", response["sources"][0]["source_id"])
        self.assertEqual([], response["contradictions"])
        self.assertEqual("high", response["confidence"])

    def test_openapi_includes_expected_paths(self) -> None:
        paths = self.app.openapi()["paths"]

        self.assertIn("/", paths)
        self.assertIn("/demo", paths)
        self.assertIn("/health", paths)
        self.assertIn("/query", paths)
        self.assertIn("/ingest", paths)
        self.assertIn("/sync/confluence", paths)
        self.assertIn("/sync/gitlab", paths)
        self.assertIn("/sync/jira", paths)
        self.assertIn("/refresh", paths)
        self.assertIn("/sync/status", paths)
        self.assertIn("/sources", paths)
        self.assertIn("/sources/{source_id}", paths)

    def test_demo_page_renders_local_ui(self) -> None:
        response = self._endpoint("/demo")()

        self.assertIn("AutoOps", response)
        self.assertIn("Refresh All Fixtures", response)
        self.assertIn("Sync Status", response)
        self.assertIn("/refresh", response)
        self.assertIn("/sync/status", response)

    def test_sync_confluence_endpoint_indexes_fixture_records(self) -> None:
        response = self._endpoint("/sync/confluence")(SyncRequest())

        self.assertEqual("success", response["status"])
        self.assertEqual("confluence-fixture", response["connection_id"])
        self.assertEqual(4, response["records_seen"])
        self.assertEqual(3, response["documents_indexed"])

    def test_sync_gitlab_endpoint_indexes_fixture_records(self) -> None:
        response = self._endpoint("/sync/gitlab")(SyncRequest())

        self.assertEqual("success", response["status"])
        self.assertEqual("gitlab-fixture", response["connection_id"])
        self.assertEqual(1, response["records_seen"])
        self.assertEqual(1, response["documents_indexed"])

    def test_sync_jira_endpoint_indexes_fixture_records(self) -> None:
        response = self._endpoint("/sync/jira")(SyncRequest())

        self.assertEqual("success", response["status"])
        self.assertEqual("jira-fixture", response["connection_id"])
        self.assertEqual(3, response["records_seen"])
        self.assertEqual(3, response["documents_indexed"])

    def test_refresh_endpoint_runs_manual_confluence_refresh(self) -> None:
        response = self._endpoint("/refresh")(
            RefreshRequest(connection="confluence", trigger="manual", lock_dir=str(Path(self.tmpdir.name) / "locks"))
        )

        self.assertEqual("success", response["status"])
        self.assertEqual("manual", response["trigger"])
        self.assertEqual("confluence", response["items"][0]["connection"])

    def test_sync_status_endpoint_returns_connection_metadata(self) -> None:
        self._endpoint("/refresh")(
            RefreshRequest(connection="all", trigger="manual", lock_dir=str(Path(self.tmpdir.name) / "locks"))
        )

        response = self._endpoint("/sync/status")()

        self.assertEqual(3, len(response["connections"]))
        self.assertEqual("confluence-fixture", response["connections"][0]["connection_id"])
        self.assertEqual("success", response["connections"][0]["last_status"])

    def _endpoint(self, path: str):
        for route in self.app.routes:
            if getattr(route, "path", None) == path:
                return route.endpoint
        raise AssertionError(f"Route not found: {path}")


if __name__ == "__main__":
    unittest.main()
