from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator


DEFAULT_FIXTURE_ROOT = Path("connector_fixtures")


def iter_fixture_files(root: Path = DEFAULT_FIXTURE_ROOT) -> Iterator[Path]:
    yield from sorted(path for path in root.rglob("*.json") if path.is_file())


def load_fixture(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Fixture must be a JSON object: {path}")
    return payload


def load_manifest(root: Path = DEFAULT_FIXTURE_ROOT) -> dict[str, Any]:
    return load_fixture(root / "manifest.json")
