from __future__ import annotations

import tempfile
from pathlib import Path

from .ingest import ingest_path
from .query import format_query_result, query_knowledge_hub
from .refresh import refresh_connections
from .safety import check_content_safety
from .storage import connect, initialize


DEMO_QUERY = "What should I do for HighKafkaConsumerLag in payments?"
SYNCED_QUERY = "Kafka consumer lag settlement replay restart"
SAFETY_SAMPLE = "Synthetic blocked customer contact: user@example.com"


def run_demo(db_path: Path | None = None) -> str:
    if db_path is None:
        with tempfile.TemporaryDirectory() as tmpdir:
            return _run_demo(Path(tmpdir) / "autoops-demo.db")
    return _run_demo(db_path)


def _run_demo(db_path: Path) -> str:
    lines: list[str] = [
        "AutoOps Judge Demo",
        "==================",
        "",
        "1. Rebuild the static mock knowledge hub.",
    ]

    ingest_summary = ingest_path(Path("mock_data"), db_path, rebuild=True)
    lines.extend(
        [
            f"   Documents indexed: {ingest_summary.documents_indexed}",
            f"   Chunks indexed: {ingest_summary.chunks_indexed}",
            f"   Blocked/errors: {ingest_summary.documents_blocked}",
            "",
            "2. Query an alert and show citations, remediation, freshness, and contradictions.",
            "",
            _indent(format_query_result(query_knowledge_hub(DEMO_QUERY, db_path, limit=6))),
            "",
            "3. Refresh fixture connectors to simulate updated Confluence, GitLab, and Jira knowledge.",
        ]
    )

    refresh_summary = refresh_connections(db_path, connection="all", trigger="manual")
    total_seen = sum(int(item.result["records_seen"]) for item in refresh_summary.items if item.result)
    total_changed = sum(int(item.result["records_changed"]) for item in refresh_summary.items if item.result)
    total_indexed = sum(int(item.result["documents_indexed"]) for item in refresh_summary.items if item.result)
    total_archived = sum(int(item.result["records_archived"]) for item in refresh_summary.items if item.result)
    lines.extend(
        [
            f"   Connections refreshed: {', '.join(item.connection for item in refresh_summary.items)}",
            f"   Records seen: {total_seen}",
            f"   Records changed: {total_changed}",
            f"   Documents indexed: {total_indexed}",
            f"   Archived records: {total_archived}",
            f"   Status: {refresh_summary.status}",
            "",
            "4. Query refreshed Kafka context and show updated fixture sources.",
            "",
            _indent(format_query_result(query_knowledge_hub(SYNCED_QUERY, db_path, limit=5))),
            "",
            "5. Verify safety screening blocks unsafe content before storage.",
        ]
    )

    safety = check_content_safety(SAFETY_SAMPLE)
    lines.extend(
        [
            f"   Safety allowed: {safety.allowed}",
            f"   Finding count: {len(safety.findings)}",
            "   Unsafe sample was evaluated only by the safety gate and was not ingested.",
            "",
            "6. Verify sync metadata exists.",
        ]
    )

    conn = connect(db_path)
    try:
        initialize(conn)
        state = conn.execute(
            """
            SELECT last_status, records_seen, records_changed, sync_cursor
            FROM sync_state
            WHERE connection_id = 'confluence-fixture'
            """
        ).fetchone()
    finally:
        conn.close()

    if state:
        lines.extend(
            [
                f"   Last status: {state['last_status']}",
                f"   Records seen: {state['records_seen']}",
                f"   Records changed: {state['records_changed']}",
                f"   Sync cursor: {state['sync_cursor']}",
            ]
        )
    else:
        lines.append("   No sync metadata found.")

    lines.extend(
        [
            "",
            f"Demo database: {db_path}",
            "Live connectors are intentionally disabled until account, token, scope, and allowlist setup is approved.",
        ]
    )
    return "\n".join(lines)


def _indent(text: str) -> str:
    return "\n".join(f"   {line}" if line else "" for line in text.splitlines())
