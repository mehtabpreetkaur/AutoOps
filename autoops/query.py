from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .storage import connect, initialize


REMEDIATION_VERBS = (
    "check",
    "verify",
    "confirm",
    "review",
    "restart",
    "monitor",
    "escalate",
    "pause",
    "reduce",
    "continue",
    "follow",
)
STOP_WORDS = {
    "about",
    "after",
    "alert",
    "and",
    "are",
    "for",
    "from",
    "how",
    "into",
    "should",
    "that",
    "the",
    "this",
    "what",
    "when",
    "where",
    "with",
}
REMEDIATION_WARNING = (
    "These remediation steps are generated from retrieved AutoOps sources and may be incomplete "
    "or incorrect. The on-call engineer must verify them before taking action."
)
SOURCE_PRIORITY = {
    "confluence": 0,
    "google_docs": 1,
    "gitlab": 2,
    "pagerduty": 3,
    "jira": 4,
    "slack": 5,
}
STALE_RELATIVE_DAYS = 14
CONTRADICTION_RULES = (
    {
        "rule_id": "restart_scope_conflict",
        "summary": "Restart scope differs between matched sources.",
        "positive": (r"\brestart all\b", r"\brestart .* immediately\b"),
        "negative": (r"\brestart one\b", r"\bdo not restart the whole\b"),
    },
    {
        "rule_id": "restart_prerequisite_conflict",
        "summary": "Restart timing differs between matched sources.",
        "positive": (r"\brestart .* immediately\b",),
        "negative": (r"\bfirst check\b", r"\bafter confirming\b", r"\bconfirm .* before restarting\b"),
    },
)


@dataclass(frozen=True)
class QueryResult:
    query: str
    answer: str
    remediation_warning: str
    recommended_remediation_steps: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    timeline_notes: list[str]
    contradictions: list[dict[str, Any]]
    gaps: list[str]
    confidence: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "answer": self.answer,
            "recommended_remediation_steps": self.recommended_remediation_steps,
            "remediation_warning": self.remediation_warning,
            "sources": self.sources,
            "timeline_notes": self.timeline_notes,
            "contradictions": self.contradictions,
            "gaps": self.gaps,
            "confidence": self.confidence,
        }


def query_knowledge_hub(query: str, db_path: Path, limit: int = 6) -> QueryResult:
    conn = connect(db_path)
    try:
        initialize(conn)
        rows = _search(conn, query, limit)
        if not rows:
            return QueryResult(
                query=query,
                answer="Insufficient evidence: no indexed AutoOps sources matched this query.",
                remediation_warning=REMEDIATION_WARNING,
                recommended_remediation_steps=[],
                sources=[],
                timeline_notes=[],
                contradictions=[],
                gaps=["No matching source chunks were found in the local knowledge hub."],
                confidence="low",
            )

        sources = [_source_from_row(row) for row in rows]
        steps = _extract_remediation_steps(rows)
        contradictions = _detect_contradictions(rows)
        timeline_notes = _timeline_notes(sources)
        gaps = _gaps(sources, steps)
        confidence = _confidence(sources, steps, contradictions)
        answer = _answer(sources, steps, contradictions)

        return QueryResult(
            query=query,
            answer=answer,
            remediation_warning=REMEDIATION_WARNING,
            recommended_remediation_steps=steps,
            sources=sources,
            timeline_notes=timeline_notes,
            contradictions=contradictions,
            gaps=gaps,
            confidence=confidence,
        )
    finally:
        conn.close()


def format_query_result(result: QueryResult) -> str:
    data = result.as_dict()
    lines = [
        "Answer:",
        data["answer"],
        "",
        "Recommended Remediation Steps:",
    ]
    if data["recommended_remediation_steps"]:
        for index, step in enumerate(data["recommended_remediation_steps"], start=1):
            source_ids = ", ".join(step["source_ids"])
            lines.append(f"{index}. {step['step']} [{source_ids}]")
    else:
        lines.append("No source-supported remediation steps found.")

    lines.extend(["", "Warning:", data["remediation_warning"], "", "Sources:"])
    for index, source in enumerate(data["sources"], start=1):
        stale = " deprecated" if source["deprecated"] else ""
        lines.append(
            f"{index}. {source['source_id']} | {source['source_type']} | {source['title']} | "
            f"updated {source['updated_at']} | {source['source_path']}{stale}"
        )

    lines.extend(["", "Timeline Notes:"])
    lines.extend(f"- {note}" for note in data["timeline_notes"]) if data["timeline_notes"] else lines.append("- None.")

    lines.extend(["", "Contradictions:"])
    if data["contradictions"]:
        for contradiction in data["contradictions"]:
            source_ids = ", ".join(contradiction["source_ids"])
            lines.append(f"- {contradiction['summary']} [{source_ids}]")
    else:
        lines.append("- None detected.")

    lines.extend(["", "Gaps:"])
    lines.extend(f"- {gap}" for gap in data["gaps"]) if data["gaps"] else lines.append("- None.")

    lines.extend(["", f"Confidence: {data['confidence']}"])
    return "\n".join(lines)


def result_to_json(result: QueryResult) -> str:
    return json.dumps(result.as_dict(), indent=2, sort_keys=True)


def _search(conn: sqlite3.Connection, query: str, limit: int) -> list[sqlite3.Row]:
    fts_query = _fts_query(query)
    if not fts_query:
        return []
    matched_alerts = _matched_alert_names(conn, query)

    sql_limit = max(limit * 10, 50) if matched_alerts else limit
    rows = conn.execute(
        """
        SELECT
            c.chunk_id,
            c.chunk_text,
            d.source_id,
            d.source_type,
            d.source_path,
            d.source_url,
            d.title,
            d.service,
            d.component,
            d.alert_name,
            d.ticket_id,
            d.incident_id,
            d.thread_id,
            d.channel,
            d.owner_team,
            d.owner_contact,
            d.created_at,
            d.updated_at,
            d.version,
            d.deprecated,
            bm25(chunks_fts) AS fts_rank
        FROM chunks_fts
        JOIN chunks c ON c.chunk_id = chunks_fts.chunk_id
        JOIN documents d ON d.source_id = c.source_id
        WHERE chunks_fts MATCH ?
        ORDER BY d.deprecated ASC, fts_rank ASC, d.updated_at DESC
        LIMIT ?
        """,
        (fts_query, sql_limit),
    ).fetchall()

    if matched_alerts:
        rows = [row for row in rows if (row["alert_name"] or "").lower() in matched_alerts]

    return sorted(rows, key=lambda row: _row_sort_key(row, prefer_source_priority=bool(matched_alerts)))[:limit]


def _matched_alert_names(conn: sqlite3.Connection, query: str) -> set[str]:
    query_lower = query.lower()
    alerts = conn.execute(
        "SELECT DISTINCT alert_name FROM documents WHERE alert_name IS NOT NULL AND alert_name != ''"
    ).fetchall()
    return {row["alert_name"].lower() for row in alerts if row["alert_name"].lower() in query_lower}


def _fts_query(query: str) -> str:
    terms = []
    for term in re.findall(r"[A-Za-z0-9_]+", query):
        normalized = term.lower()
        if len(normalized) < 3 or normalized in STOP_WORDS:
            continue
        terms.append(term)
    deduped = list(dict.fromkeys(terms))
    return " OR ".join(f'"{term}"' for term in deduped)


def _row_sort_key(row: sqlite3.Row, prefer_source_priority: bool) -> tuple[int, float | int, int | float, int]:
    deprecated = int(row["deprecated"])
    source_priority = SOURCE_PRIORITY.get(row["source_type"], 99)
    fts_rank = float(row["fts_rank"])
    updated = _timestamp_sort_value(row["updated_at"])
    if prefer_source_priority:
        return (deprecated, source_priority, fts_rank, -updated)
    return (deprecated, fts_rank, source_priority, -updated)


def _source_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "source_id": row["source_id"],
        "source_type": row["source_type"],
        "title": row["title"],
        "source_path": row["source_path"],
        "source_url": row["source_url"],
        "service": row["service"],
        "component": row["component"],
        "alert_name": row["alert_name"],
        "ticket_id": row["ticket_id"],
        "incident_id": row["incident_id"],
        "thread_id": row["thread_id"],
        "channel": row["channel"],
        "owner_team": row["owner_team"],
        "owner_contact": row["owner_contact"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "version": row["version"],
        "deprecated": bool(row["deprecated"]),
        "excerpt": _excerpt(row["chunk_text"]),
    }


def _extract_remediation_steps(rows: list[sqlite3.Row], max_steps: int = 5) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        for sentence in _sentences(row["chunk_text"]):
            lower = sentence.lower()
            if not any(re.search(rf"\b{verb}\b", lower) for verb in REMEDIATION_VERBS):
                continue
            cleaned = sentence.rstrip(".")
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            steps.append({"step": cleaned + ".", "source_ids": [row["source_id"]]})
            if len(steps) >= max_steps:
                return steps
    return steps


def _timeline_notes(sources: list[dict[str, Any]]) -> list[str]:
    if not sources:
        return []

    ordered = sorted(sources, key=lambda source: source.get("updated_at") or "", reverse=True)
    newest = ordered[0]
    notes = [
        f"Newest matched source is {newest['source_id']} ({newest['source_type']}) updated at {newest['updated_at']}."
    ]
    newest_ts = _timestamp_sort_value(newest.get("updated_at"))
    deprecated = [source for source in sources if source["deprecated"]]
    for source in deprecated:
        notes.append(
            f"{source['source_id']} is marked deprecated but matched the query; review it as historical context only."
        )
    for source in ordered[1:]:
        source_ts = _timestamp_sort_value(source.get("updated_at"))
        if newest_ts and source_ts:
            age_days = int((newest_ts - source_ts) / 86400)
            source["age_days_from_newest"] = age_days
            if age_days >= STALE_RELATIVE_DAYS:
                notes.append(
                    f"{source['source_id']} is {age_days} day(s) older than the newest matched source."
                )
    if len({source["updated_at"] for source in sources if source.get("updated_at")}) > 1:
        notes.append("Matched sources span multiple update times, so review newer context before acting.")
    return notes


def _gaps(sources: list[dict[str, Any]], steps: list[dict[str, Any]]) -> list[str]:
    gaps: list[str] = []
    source_types = {source["source_type"] for source in sources}
    for expected in ("confluence", "jira", "pagerduty", "slack"):
        if expected not in source_types:
            gaps.append(f"No matching {expected} source was retrieved.")
    if not steps:
        gaps.append("No remediation step was extracted from the retrieved source text.")
    return gaps


def _detect_contradictions(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    contradictions: list[dict[str, Any]] = []
    for rule in CONTRADICTION_RULES:
        positive_matches = _rule_matches(rows, rule["positive"])
        negative_matches = _rule_matches(rows, rule["negative"])
        if not positive_matches or not negative_matches:
            continue
        source_ids = sorted({match["source_id"] for match in positive_matches + negative_matches})
        contradictions.append(
            {
                "rule_id": rule["rule_id"],
                "summary": rule["summary"],
                "source_ids": source_ids,
                "evidence": {
                    "positive": positive_matches,
                    "negative": negative_matches,
                },
            }
        )
    return contradictions


def _rule_matches(rows: list[sqlite3.Row], patterns: tuple[str, ...]) -> list[dict[str, str]]:
    matches: list[dict[str, str]] = []
    for row in rows:
        for sentence in _sentences(row["chunk_text"]):
            lower = sentence.lower()
            if not any(re.search(pattern, lower) for pattern in patterns):
                continue
            matches.append(
                {
                    "source_id": row["source_id"],
                    "source_type": row["source_type"],
                    "excerpt": sentence,
                }
            )
            break
    return matches


def _confidence(
    sources: list[dict[str, Any]],
    steps: list[dict[str, Any]],
    contradictions: list[dict[str, Any]],
) -> str:
    active_sources = [source for source in sources if not source["deprecated"]]
    source_types = {source["source_type"] for source in active_sources}
    if contradictions:
        return "medium" if len(active_sources) >= 2 and steps else "low"
    if len(active_sources) >= 3 and steps and {"confluence", "jira", "pagerduty"}.issubset(source_types):
        return "high"
    if len(active_sources) >= 2 and steps:
        return "medium"
    return "low"


def _answer(
    sources: list[dict[str, Any]],
    steps: list[dict[str, Any]],
    contradictions: list[dict[str, Any]],
) -> str:
    active_sources = [source for source in sources if not source["deprecated"]]
    top_source = active_sources[0] if active_sources else sources[0]
    contradiction_note = (
        f" {len(contradictions)} contradiction(s) were flagged for review."
        if contradictions
        else ""
    )
    if steps:
        return (
            f"Found {len(sources)} relevant source(s). Start with {top_source['title']} "
            f"({top_source['source_id']}) and review the cited remediation steps before acting."
            f"{contradiction_note}"
        )
    return (
        f"Found {len(sources)} relevant source(s), but no explicit remediation step was extracted. "
        f"Start with {top_source['title']} ({top_source['source_id']}) for context."
        f"{contradiction_note}"
    )


def _sentences(text: str) -> list[str]:
    return [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text) if sentence.strip()]


def _excerpt(text: str, max_length: int = 260) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 3].rstrip() + "..."


def _timestamp_sort_value(value: str | None) -> int:
    if not value:
        return 0
    try:
        normalized = value.replace("Z", "+00:00")
        return int(datetime.fromisoformat(normalized).timestamp())
    except ValueError:
        return 0
