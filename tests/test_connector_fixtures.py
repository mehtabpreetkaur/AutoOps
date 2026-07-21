import json
import sqlite3
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

from autoops.fixtures import DEFAULT_FIXTURE_ROOT, iter_fixture_files, load_fixture, load_manifest
from autoops.safety import check_content_safety
from autoops.storage import connect, initialize


EXPECTED_SOURCES = {
    "confluence",
    "gitlab",
    "google_drive",
    "google_docs",
    "jira",
    "pagerduty",
    "slack",
}

EXPECTED_SCENARIOS = {
    "first_sync",
    "incremental_changed_record",
    "deleted_or_archived_record",
    "jira_non_pagerduty_ticket",
    "thread_replies",
    "blocked_payload_placeholder",
}


class ConnectorFixtureTests(unittest.TestCase):
    def test_manifest_covers_expected_sources_and_scenarios(self) -> None:
        manifest = load_manifest()

        self.assertEqual(EXPECTED_SOURCES, set(manifest["sources"]))
        self.assertEqual(EXPECTED_SCENARIOS, {item["scenario"] for item in manifest["matrix"]})

    def test_all_manifest_fixture_refs_exist(self) -> None:
        manifest = load_manifest()

        for item in manifest["matrix"]:
            for fixture_ref in item["fixture_refs"]:
                self.assertTrue((DEFAULT_FIXTURE_ROOT / fixture_ref).exists(), fixture_ref)

    def test_all_fixtures_are_json_objects_and_pass_safety_gate(self) -> None:
        fixture_files = list(iter_fixture_files())

        self.assertGreaterEqual(len(fixture_files), 13)
        for path in fixture_files:
            payload = load_fixture(path)
            self.assertIsInstance(payload, dict)

            raw_text = json.dumps(payload, sort_keys=True)
            result = check_content_safety(raw_text)
            self.assertTrue(result.allowed, f"{path}: {result.findings}")

    def test_each_source_has_at_least_one_fixture_file(self) -> None:
        fixture_sources = {path.parent.name for path in iter_fixture_files() if path.name != "manifest.json"}

        self.assertTrue(EXPECTED_SOURCES.issubset(fixture_sources))

    def test_jira_non_pagerduty_fixtures_have_no_pagerduty_assumption(self) -> None:
        access_request = load_fixture(DEFAULT_FIXTURE_ROOT / "jira/issue_access_request.json")
        prod_change = load_fixture(DEFAULT_FIXTURE_ROOT / "jira/issue_prod_change.json")

        self.assertEqual("Access Request", access_request["fields"]["issuetype"]["name"])
        self.assertEqual("Change", prod_change["fields"]["issuetype"]["name"])
        self.assertNotIn("pagerduty", json.dumps(access_request).lower())
        self.assertNotIn("pagerduty", json.dumps(prod_change).lower())

    def test_fixture_payload_can_be_recorded_as_hash_only_raw_source_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            conn = connect(Path(tmpdir) / "autoops.db")
            try:
                initialize(conn)
                conn.execute(
                    """
                    INSERT INTO source_connections (
                        connection_id, source_type, display_name
                    ) VALUES ('confluence-fixture', 'confluence', 'Confluence Fixture')
                    """
                )
                fixture_path = DEFAULT_FIXTURE_ROOT / "confluence/page_current.json"
                raw = fixture_path.read_text(encoding="utf-8")
                payload = load_fixture(fixture_path)
                conn.execute(
                    """
                    INSERT INTO raw_source_records (
                        raw_id, connection_id, source_type, external_id, external_version,
                        external_updated_at, payload_hash, payload_storage_mode
                    ) VALUES (
                        'raw-fixture-1', 'confluence-fixture', 'confluence', ?, ?, ?, ?, 'hash_only'
                    )
                    """,
                    (
                        payload["id"],
                        str(payload["version"]["number"]),
                        payload["version"]["createdAt"],
                        sha256(raw.encode("utf-8")).hexdigest(),
                    ),
                )
                row = conn.execute(
                    """
                    SELECT external_id, external_version, payload_storage_mode, sanitized_payload_json
                    FROM raw_source_records
                    WHERE raw_id = 'raw-fixture-1'
                    """
                ).fetchone()

                self.assertEqual("conf-page-1001", row["external_id"])
                self.assertEqual("3", row["external_version"])
                self.assertEqual("hash_only", row["payload_storage_mode"])
                self.assertIsNone(row["sanitized_payload_json"])
            finally:
                conn.close()

    def test_duplicate_fixture_raw_source_version_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            conn = connect(Path(tmpdir) / "autoops.db")
            try:
                initialize(conn)
                conn.execute(
                    """
                    INSERT INTO source_connections (
                        connection_id, source_type, display_name
                    ) VALUES ('confluence-fixture', 'confluence', 'Confluence Fixture')
                    """
                )
                insert_sql = """
                    INSERT INTO raw_source_records (
                        raw_id, connection_id, source_type, external_id, external_version, payload_hash
                    ) VALUES (?, 'confluence-fixture', 'confluence', 'conf-page-1001', '3', ?)
                """
                conn.execute(insert_sql, ("raw-1", "hash-1"))

                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(insert_sql, ("raw-2", "hash-2"))
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
