from __future__ import annotations

import hashlib
import json
import math
import re


EMBEDDING_MODEL = "autoops-hash-embedding-v0"
EMBEDDING_DIMENSIONS = 96

_STOP_WORDS = {
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
_SYNONYMS = {
    "backlog": ("lag", "behind"),
    "delayed": ("lag", "behind"),
    "responsible": ("owner", "ownership"),
    "owns": ("owner", "ownership"),
    "team": ("owner", "ownership"),
    "contact": ("owner", "oncall"),
    "remediate": ("mitigate", "fix"),
    "fix": ("mitigate", "remediate"),
}


def embed_text(text: str, dimensions: int = EMBEDDING_DIMENSIONS) -> list[float]:
    """Return a deterministic, local embedding suitable for prototype hybrid retrieval."""
    vector = [0.0] * dimensions
    tokens = _tokens(text)
    features = tokens + _token_bigrams(tokens)
    if not features:
        return vector

    for feature in features:
        digest = hashlib.sha256(feature.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        weight = 1.35 if " " in feature else 1.0
        vector[bucket] += sign * weight

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [round(value / norm, 6) for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True))


def serialize_embedding(vector: list[float]) -> str:
    return json.dumps(vector, separators=(",", ":"))


def deserialize_embedding(payload: str | None) -> list[float]:
    if not payload:
        return []
    data = json.loads(payload)
    if not isinstance(data, list):
        return []
    return [float(value) for value in data]


def _tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for raw_token in re.findall(r"[A-Za-z0-9_]+", text):
        token = raw_token.lower()
        if len(token) < 3 or token in _STOP_WORDS:
            continue
        tokens.append(token)
        tokens.extend(_SYNONYMS.get(token, ()))
    return tokens


def _token_bigrams(tokens: list[str]) -> list[str]:
    return [f"{left} {right}" for left, right in zip(tokens, tokens[1:], strict=False)]
