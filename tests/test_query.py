import tempfile
import unittest
from pathlib import Path

from autoops.ingest import ingest_path
from autoops.query import query_knowledge_hub


class QueryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "autoops.db"
        ingest_path(Path("mock_data"), self.db_path, rebuild=True)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_kafka_query_returns_citations_remediation_freshness_and_contradictions(self) -> None:
        result = query_knowledge_hub("What should I do for HighKafkaConsumerLag in payments?", self.db_path)
        data = result.as_dict()

        self.assertEqual("mock-conf-001", data["sources"][0]["source_id"])
        self.assertGreaterEqual(len(data["sources"]), 5)
        self.assertNotIn("mock-gdoc-001", {source["source_id"] for source in data["sources"]})
        self.assertGreaterEqual(len(data["recommended_remediation_steps"]), 1)
        self.assertTrue(data["remediation_warning"])
        self.assertEqual("medium", data["confidence"])

        contradiction_ids = {item["rule_id"] for item in data["contradictions"]}
        self.assertIn("restart_scope_conflict", contradiction_ids)
        self.assertIn("restart_prerequisite_conflict", contradiction_ids)
        self.assertTrue(any("Newest matched source" in note for note in data["timeline_notes"]))
        self.assertTrue(any("deprecated" in note for note in data["timeline_notes"]))

    def test_clean_orders_query_has_no_contradictions_and_high_confidence(self) -> None:
        result = query_knowledge_hub("DatabaseConnectionPoolSaturation in orders-api", self.db_path)
        data = result.as_dict()

        self.assertEqual("mock-conf-002", data["sources"][0]["source_id"])
        self.assertEqual([], data["contradictions"])
        self.assertEqual("high", data["confidence"])
        self.assertGreaterEqual(len(data["recommended_remediation_steps"]), 1)
        self.assertEqual([], data["gaps"])

    def test_partial_memory_query_reports_missing_source_gaps(self) -> None:
        result = query_knowledge_hub("MemoryPressureHigh search index worker", self.db_path)
        data = result.as_dict()

        source_types = {source["source_type"] for source in data["sources"]}
        self.assertEqual({"jira", "slack"}, source_types)
        self.assertIn("No matching confluence source was retrieved.", data["gaps"])
        self.assertIn("No matching pagerduty source was retrieved.", data["gaps"])
        self.assertEqual("medium", data["confidence"])

    def test_ownership_query_returns_context_without_remediation(self) -> None:
        result = query_knowledge_hub("payments ownership map settlement replay", self.db_path, limit=1)
        data = result.as_dict()

        self.assertEqual("fts", data["search_mode"])
        self.assertEqual("mock-gdoc-002", data["sources"][0]["source_id"])
        self.assertEqual([], data["recommended_remediation_steps"])
        self.assertNotIn("No remediation step was extracted from the retrieved source text.", data["gaps"])
        self.assertEqual("medium", data["confidence"])

    def test_experimental_hybrid_search_returns_scores_and_structured_owner_context(self) -> None:
        result = query_knowledge_hub(
            "responsible team payments consumer backlog",
            self.db_path,
            limit=3,
            search_mode="hybrid",
        )
        data = result.as_dict()

        self.assertEqual("hybrid", data["search_mode"])
        self.assertEqual("ownership", data["query_intent"])
        self.assertGreaterEqual(len(data["sources"]), 1)
        self.assertEqual("payments-platform", data["sources"][0]["owner_team"])
        self.assertIn("payments-platform appears to own", data["answer"])
        self.assertEqual([], data["recommended_remediation_steps"])
        self.assertIn("retrieval_scores", data["sources"][0])
        self.assertIn("hybrid", data["sources"][0]["retrieval_scores"])

    def test_long_checkout_runbook_query_returns_multiple_chunks_from_same_source(self) -> None:
        result = query_knowledge_hub("CheckoutLatencyHigh checkout-api dependency latency", self.db_path)
        data = result.as_dict()

        source_ids = [source["source_id"] for source in data["sources"]]
        self.assertIn("mock-conf-003", source_ids)
        self.assertGreaterEqual(source_ids.count("mock-conf-003"), 2)
        self.assertGreaterEqual(len(data["recommended_remediation_steps"]), 1)

    def test_planned_maintenance_query_surfaces_calendar_context_first(self) -> None:
        result = query_knowledge_hub("planned maintenance payments settlement replay", self.db_path)
        data = result.as_dict()

        self.assertEqual("mock-gdoc-003", data["sources"][0]["source_id"])
        self.assertIn("maintenance window", data["recommended_remediation_steps"][0]["step"])
        self.assertIn("No matching pagerduty source was retrieved.", data["gaps"])

    def test_access_request_query_handles_non_pagerduty_jira_ticket(self) -> None:
        result = query_knowledge_hub("access request payments runbook space", self.db_path)
        data = result.as_dict()

        self.assertEqual("mock-jira-004", data["sources"][0]["source_id"])
        self.assertEqual("OPS-5001", data["sources"][0]["ticket_id"])
        self.assertIsNone(data["sources"][0]["alert_name"])
        self.assertIn("access request", data["sources"][0]["title"].lower())

    def test_production_change_query_returns_change_ticket_and_slack_thread(self) -> None:
        result = query_knowledge_hub("production change checkout cache rollout latency", self.db_path)
        data = result.as_dict()

        source_ids = [source["source_id"] for source in data["sources"]]
        self.assertEqual("mock-jira-005", source_ids[0])
        self.assertIn("mock-slack-004", source_ids)
        self.assertGreaterEqual(len(data["recommended_remediation_steps"]), 2)

    def test_deprecated_payment_gateway_query_flags_legacy_source(self) -> None:
        result = query_knowledge_hub("PaymentGatewayTimeoutRateHigh legacy timeout", self.db_path)
        data = result.as_dict()

        source_ids = [source["source_id"] for source in data["sources"]]
        self.assertEqual(["mock-gdoc-001", "mock-conf-004"], source_ids)
        self.assertTrue(data["sources"][1]["deprecated"])
        self.assertTrue(any("mock-conf-004 is marked deprecated" in note for note in data["timeline_notes"]))
        self.assertEqual("low", data["confidence"])

    def test_unknown_query_returns_insufficient_evidence_without_remediation(self) -> None:
        result = query_knowledge_hub("zzzzzzzz qqqqqqqq", self.db_path)
        data = result.as_dict()

        self.assertEqual([], data["sources"])
        self.assertEqual([], data["recommended_remediation_steps"])
        self.assertEqual([], data["contradictions"])
        self.assertEqual("low", data["confidence"])
        self.assertIn("Insufficient evidence", data["answer"])


if __name__ == "__main__":
    unittest.main()
