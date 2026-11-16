"""Similar-incident retrieval from SQLite memory (Concept 1).

A deliberately transparent scoring method students can read and tweak:

    score = 0.45 * keyword overlap (Jaccard)
          + 0.35 * log-pattern overlap
          + 0.20 * same service

Semantic (embedding) search would be a natural upgrade, but simple scoring
is easy to explain and has no extra dependencies.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from memory.incident_repository import list_incidents

STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "was", "were", "are", "has", "had", "have",
    "not", "but", "into", "after", "before", "when", "then", "than", "service", "error", "errors",
    "failed", "failure", "issue", "incident", "users", "user", "some", "many", "very", "high", "low",
    "runbook", "runbooks",
}


def tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-z][a-z0-9_\-]{2,}", (text or "").lower())
    return {w for w in words if w not in STOPWORDS}


def incident_text(inc: dict[str, Any]) -> str:
    return " ".join(str(inc.get(k, "")) for k in
                    ("title", "description", "symptoms", "root_cause", "resolution", "lessons_learned"))


def score_incident(query_tokens: set[str], query_patterns: set[str], service: str,
                   inc: dict[str, Any]) -> tuple[float, list[str]]:
    inc_tokens = tokenize(incident_text(inc))
    shared = query_tokens & inc_tokens
    jaccard = len(shared) / len(query_tokens | inc_tokens) if (query_tokens or inc_tokens) else 0.0
    inc_patterns = set(inc.get("log_patterns") or [])
    pattern_overlap = len(query_patterns & inc_patterns) / len(query_patterns) if query_patterns else 0.0
    same_service = 1.0 if service and inc.get("service") == service else 0.0
    score = 0.45 * min(1.0, jaccard * 3) + 0.35 * pattern_overlap + 0.20 * same_service
    reasons = sorted(shared)[:8]
    if query_patterns & inc_patterns:
        reasons += [f"pattern:{p}" for p in sorted(query_patterns & inc_patterns)]
    if same_service:
        reasons.append(f"service:{service}")
    return round(score, 3), reasons


def retrieve_similar_incidents(query: str, service: str = "", patterns: list[str] | None = None,
                               top_k: int = 3, exclude_id: str | None = None, min_score: float = 0.12,
                               db_path: str | Path | None = None) -> list[dict[str, Any]]:
    q_tokens = tokenize(query)
    q_patterns = set(patterns or [])
    results = []
    for inc in list_incidents(db_path, limit=1000):
        if inc["id"] == exclude_id:
            continue
        # Only incidents with a known outcome are useful as "memory".
        if not (inc.get("root_cause") or inc.get("resolution")):
            continue
        score, reasons = score_incident(q_tokens, q_patterns, service, inc)
        if score >= min_score:
            results.append({
                "id": inc["id"], "title": inc["title"], "service": inc["service"], "severity": inc["severity"],
                "created_at": inc["created_at"], "root_cause": inc.get("root_cause", ""),
                "resolution": inc.get("resolution", ""), "lessons_learned": inc.get("lessons_learned", ""),
                "score": score, "matched_on": reasons,
            })
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[: max(1, min(int(top_k), 5))]
