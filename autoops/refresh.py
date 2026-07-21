from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from .connectors import sync_confluence_fixture, sync_gitlab_fixture, sync_jira_fixture
from .connectors.base import SyncResult


SUPPORTED_CONNECTIONS = ("confluence", "gitlab", "jira")
DEFAULT_LOCK_DIR = Path("data/sync_locks")


@dataclass(frozen=True)
class RefreshItem:
    connection: str
    trigger: str
    status: str
    locked: bool
    result: dict[str, object] | None
    message: str


@dataclass(frozen=True)
class RefreshSummary:
    trigger: str
    requested_connections: list[str]
    started_at: str
    completed_at: str
    status: str
    items: list[RefreshItem]

    def as_dict(self) -> dict[str, object]:
        return {
            "trigger": self.trigger,
            "requested_connections": self.requested_connections,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "items": [asdict(item) for item in self.items],
        }


class ConnectorLock:
    def __init__(self, lock_path: Path) -> None:
        self.lock_path = lock_path
        self.token = str(uuid.uuid4())
        self.acquired = False

    def __enter__(self) -> "ConnectorLock":
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            self.acquired = False
            return self

        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"token": self.token, "created_at": _now()}, sort_keys=True))
        self.acquired = True
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if not self.acquired:
            return
        try:
            payload = json.loads(self.lock_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return
        if payload.get("token") == self.token:
            self.lock_path.unlink(missing_ok=True)


def refresh_connections(
    db_path: Path,
    connection: str = "all",
    trigger: str = "manual",
    fixture_root: Path = Path("connector_fixtures"),
    lock_dir: Path = DEFAULT_LOCK_DIR,
    dry_run: bool = False,
) -> RefreshSummary:
    if trigger not in {"manual", "scheduled"}:
        raise ValueError("trigger must be 'manual' or 'scheduled'.")

    requested = _resolve_connections(connection)
    started_at = _now()
    items: list[RefreshItem] = []

    for item_connection in requested:
        lock_path = lock_dir / f"{item_connection}.lock"
        with ConnectorLock(lock_path) as lock:
            if not lock.acquired:
                items.append(
                    RefreshItem(
                        connection=item_connection,
                        trigger=trigger,
                        status="locked",
                        locked=True,
                        result=None,
                        message=f"Skipped {item_connection}: another refresh is already running.",
                    )
                )
                continue

            result = _run_connection(item_connection, db_path, fixture_root, dry_run)
            items.append(
                RefreshItem(
                    connection=item_connection,
                    trigger=trigger,
                    status=result.status,
                    locked=False,
                    result=asdict(result),
                    message=result.message,
                )
            )

    completed_at = _now()
    status = _summary_status(items)
    return RefreshSummary(
        trigger=trigger,
        requested_connections=requested,
        started_at=started_at,
        completed_at=completed_at,
        status=status,
        items=items,
    )


def format_refresh_summary(summary: RefreshSummary) -> str:
    lines = [
        "Refresh Summary",
        f"Trigger: {summary.trigger}",
        f"Status: {summary.status}",
        f"Started: {summary.started_at}",
        f"Completed: {summary.completed_at}",
        "Connections:",
    ]
    for item in summary.items:
        lines.append(f"- {item.connection}: {item.status} | {item.message}")
        if item.result:
            lines.append(
                "  "
                f"seen={item.result['records_seen']} "
                f"changed={item.result['records_changed']} "
                f"indexed={item.result['documents_indexed']} "
                f"archived={item.result['records_archived']} "
                f"blocked={item.result['records_blocked']}"
            )
    return "\n".join(lines)


def _resolve_connections(connection: str) -> list[str]:
    if connection == "all":
        return list(SUPPORTED_CONNECTIONS)
    if connection not in SUPPORTED_CONNECTIONS:
        raise ValueError(f"Unsupported connection: {connection}")
    return [connection]


def _run_connection(connection: str, db_path: Path, fixture_root: Path, dry_run: bool) -> SyncResult:
    if connection == "confluence":
        return sync_confluence_fixture(db_path, fixture_root=fixture_root, dry_run=dry_run)
    if connection == "gitlab":
        return sync_gitlab_fixture(db_path, fixture_root=fixture_root, dry_run=dry_run)
    if connection == "jira":
        return sync_jira_fixture(db_path, fixture_root=fixture_root, dry_run=dry_run)
    raise ValueError(f"Unsupported connection: {connection}")


def _summary_status(items: list[RefreshItem]) -> str:
    if any(item.status == "error" for item in items):
        return "error"
    if any(item.status == "locked" for item in items):
        return "partial"
    if all(item.status == "dry_run" for item in items):
        return "dry_run"
    return "success"


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
