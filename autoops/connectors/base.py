from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    mode: str
    message: str


@dataclass(frozen=True)
class RawRecord:
    source_type: str
    external_id: str
    external_url: str | None
    external_version: str | None
    external_created_at: str | None
    external_updated_at: str | None
    payload_hash: str
    payload: dict[str, Any]
    deleted_or_archived: bool = False
    fixture_path: Path | None = None


@dataclass(frozen=True)
class FetchResult:
    records: list[RawRecord]
    next_cursor: str | None

    @property
    def records_seen(self) -> int:
        return len(self.records)


@dataclass(frozen=True)
class SyncResult:
    connection_id: str
    source_type: str
    mode: str
    dry_run: bool
    records_seen: int
    records_changed: int
    documents_indexed: int
    records_archived: int
    records_blocked: int
    status: str
    message: str


class Connector(Protocol):
    connection_id: str
    source_type: str
    mode: str

    def validate_connection(self) -> ValidationResult: ...

    def fetch_changes(self, cursor: str | None = None) -> FetchResult: ...

    def normalize(self, raw_record: RawRecord) -> dict[str, Any]: ...
