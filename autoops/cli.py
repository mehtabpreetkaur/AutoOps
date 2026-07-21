from __future__ import annotations

import argparse
import json
from pathlib import Path

from .api import add_api_parser, run_server
from .connectors import sync_confluence_fixture, sync_gitlab_fixture, sync_jira_fixture
from .demo import run_demo
from .ingest import ingest_path
from .query import format_query_result, query_knowledge_hub, result_to_json
from .refresh import format_refresh_summary, refresh_connections


DEFAULT_DB_PATH = Path("data/autoops.db")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="autoops", description="AutoOps SRE knowledge hub prototype CLI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="Manually ingest mock JSON sources.")
    ingest_parser.add_argument("source_root", type=Path, help="Directory containing mock JSON source files.")
    ingest_parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite database path.")
    ingest_parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Clear existing indexed data before ingestion.",
    )

    query_parser = subparsers.add_parser("query", help="Query the local AutoOps knowledge hub.")
    query_parser.add_argument("query", help="Question or alert/ticket context to search for.")
    query_parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite database path.")
    query_parser.add_argument("--limit", type=int, default=6, help="Maximum source chunks to retrieve.")
    query_parser.add_argument(
        "--search-mode",
        choices=["fts", "hybrid"],
        default="fts",
        help="Retrieval mode. 'hybrid' is experimental and combines FTS, local embeddings, and metadata boosts.",
    )
    query_parser.add_argument("--json", action="store_true", help="Print structured JSON output.")

    sync_parser = subparsers.add_parser("sync", help="Run an approved Phase 2 fixture connector sync.")
    sync_parser.add_argument("connector", choices=["confluence", "gitlab", "jira"], help="Connector to sync.")
    sync_parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite database path.")
    sync_parser.add_argument(
        "--fixture-root",
        type=Path,
        default=Path("connector_fixtures"),
        help="Directory containing connector fixture payloads.",
    )
    sync_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and normalize fixture records without writing to SQLite.",
    )

    refresh_parser = subparsers.add_parser(
        "refresh",
        help="Run manual or cron-compatible scheduled connector refreshes.",
    )
    refresh_parser.add_argument(
        "--connection",
        choices=["all", "confluence", "gitlab", "jira"],
        default="all",
        help="Connection to refresh.",
    )
    refresh_parser.add_argument(
        "--trigger",
        choices=["manual", "scheduled"],
        default="manual",
        help="Refresh trigger label for audit/status output.",
    )
    refresh_parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite database path.")
    refresh_parser.add_argument(
        "--fixture-root",
        type=Path,
        default=Path("connector_fixtures"),
        help="Directory containing connector fixture payloads.",
    )
    refresh_parser.add_argument(
        "--lock-dir",
        type=Path,
        default=Path("data/sync_locks"),
        help="Directory for per-connector lock files.",
    )
    refresh_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate refresh work without writing connector records.",
    )
    refresh_parser.add_argument("--json", action="store_true", help="Print structured JSON output.")

    demo_parser = subparsers.add_parser("demo", help="Run the judge-ready AutoOps demo flow.")
    demo_parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Optional SQLite database path. Defaults to a temporary demo database.",
    )

    add_api_parser(subparsers, DEFAULT_DB_PATH)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "ingest":
        summary = ingest_path(args.source_root, args.db, rebuild=args.rebuild)
        print(f"Database: {summary.db_path}")
        print(f"Documents seen: {summary.documents_seen}")
        print(f"Documents indexed: {summary.documents_indexed}")
        print(f"Documents blocked/errors: {summary.documents_blocked}")
        print(f"Chunks indexed: {summary.chunks_indexed}")
    elif args.command == "query":
        result = query_knowledge_hub(args.query, args.db, limit=args.limit, search_mode=args.search_mode)
        print(result_to_json(result) if args.json else format_query_result(result))
    elif args.command == "sync":
        if args.connector == "confluence":
            summary = sync_confluence_fixture(args.db, fixture_root=args.fixture_root, dry_run=args.dry_run)
        elif args.connector == "gitlab":
            summary = sync_gitlab_fixture(args.db, fixture_root=args.fixture_root, dry_run=args.dry_run)
        elif args.connector == "jira":
            summary = sync_jira_fixture(args.db, fixture_root=args.fixture_root, dry_run=args.dry_run)
        else:
            parser.error(f"Unsupported connector: {args.connector}")
            return
        if args.connector in {"confluence", "gitlab", "jira"}:
            print(f"Connection: {summary.connection_id}")
            print(f"Source type: {summary.source_type}")
            print(f"Mode: {summary.mode}")
            print(f"Dry run: {summary.dry_run}")
            print(f"Records seen: {summary.records_seen}")
            print(f"Records changed: {summary.records_changed}")
            print(f"Documents indexed: {summary.documents_indexed}")
            print(f"Records archived: {summary.records_archived}")
            print(f"Records blocked: {summary.records_blocked}")
            print(f"Status: {summary.status}")
            print(f"Message: {summary.message}")
    elif args.command == "refresh":
        summary = refresh_connections(
            args.db,
            connection=args.connection,
            trigger=args.trigger,
            fixture_root=args.fixture_root,
            lock_dir=args.lock_dir,
            dry_run=args.dry_run,
        )
        print(json.dumps(summary.as_dict(), indent=2, sort_keys=True) if args.json else format_refresh_summary(summary))
    elif args.command == "demo":
        print(run_demo(args.db))
    elif args.command == "serve":
        run_server(args.host, args.port, args.db)
