from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class SafetySeverity(str, Enum):
    BLOCK = "block"
    WARN = "warn"


@dataclass(frozen=True)
class SafetyFinding:
    severity: SafetySeverity
    rule_id: str
    message: str


@dataclass(frozen=True)
class SafetyResult:
    allowed: bool
    findings: list[SafetyFinding]


SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "private_key",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        "Private key material is not allowed in the knowledge store.",
    ),
    (
        "aws_access_key",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "Cloud access keys are not allowed in the knowledge store.",
    ),
    (
        "bearer_token",
        re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}\b", re.IGNORECASE),
        "Bearer tokens are not allowed in the knowledge store.",
    ),
    (
        "password_assignment",
        re.compile(r"\b(password|passwd|pwd)\s*[:=]\s*\S+", re.IGNORECASE),
        "Password-like assignments are not allowed in the knowledge store.",
    ),
    (
        "api_key_assignment",
        re.compile(r"\b(api[_-]?key|secret|token)\s*[:=]\s*\S+", re.IGNORECASE),
        "Secret-like assignments are not allowed in the knowledge store.",
    ),
)

EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
ALLOWED_OPERATIONAL_EMAIL_DOMAINS = {"example.internal"}


def check_content_safety(text: str) -> SafetyResult:
    findings: list[SafetyFinding] = []

    for rule_id, pattern, message in SECRET_PATTERNS:
        if pattern.search(text):
            findings.append(SafetyFinding(SafetySeverity.BLOCK, rule_id, message))

    for match in EMAIL_PATTERN.finditer(text):
        domain = match.group(1).lower()
        if domain not in ALLOWED_OPERATIONAL_EMAIL_DOMAINS:
            findings.append(
                SafetyFinding(
                    SafetySeverity.BLOCK,
                    "customer_or_external_email",
                    "External or customer email addresses are not allowed in Phase 1 mock data.",
                )
            )
            break

    return SafetyResult(
        allowed=not any(finding.severity == SafetySeverity.BLOCK for finding in findings),
        findings=findings,
    )
