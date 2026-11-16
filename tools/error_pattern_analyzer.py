"""Error Pattern Analyzer - deterministic catalogue of known failure SYMPTOMS.

Used by the Log Analyzer and exposed to the agent as the
`search_error_patterns` tool. Everything here is plain regular expressions:
repeatable, explainable and never invents evidence.

Labels describe symptoms ("Database timeouts"), not root causes - deciding
the cause is the agent's job, verified against this evidence.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # avoid a circular import at runtime
    from tools.log_analyzer import LogLine

# (id, human label, regex)
PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    ("db_pool_pressure", "Database connection pool pressure",
     re.compile(r"waiting=[1-9]|connection pool|pool (?:is )?exhausted|idle=0|no available connection|"
                r"waiting for (?:a )?(?:db )?connection|too many connections|pending=\d{2,}", re.I)),
    ("db_timeout", "Database timeouts",
     re.compile(r"sqltimeout|query timed out|statement timeout|connection is not available|"
                r"database[^\n]{0,40}timed? ?out|jdbc[^\n]{0,60}timeout", re.I)),
    ("slow_transaction", "Slow transactions / high latency",
     re.compile(r"slow (?:query|transaction|request)|took \d{4,}\s?ms|latency_ms=\d{4,}|duration=\d{4,}ms", re.I)),
    ("payment_errors", "Payment / checkout errors",
     re.compile(r"payment (?:failed|error|declined due)|checkout failed|(?-i:PAYMENT_[A-Z_]+)", re.I)),
    ("downstream_timeout", "Downstream dependency timeouts",
     re.compile(r"read timed out|gateway timeout|\b504\b|upstream[^\n]{0,40}(?:timeout|unavailable)|"
                r"request to \S+ (?:timed out|failed)|dependency[^\n]{0,30}(?:timeout|unavailable)", re.I)),
    ("retries", "Retries / retry storm",
     re.compile(r"retry(?:ing)? (?:attempt )?\d|attempt \d+/\d+|retries exhausted|backing off", re.I)),
    ("circuit_breaker", "Circuit breaker activity",
     re.compile(r"circuit ?breaker", re.I)),
    ("memory_pressure", "Memory pressure",
     re.compile(r"outofmemory|oomkilled|heap space|heap used=(?:[89]\d|100)%|gc overhead|memory (?:pressure|limit exceeded)|"
                r"exit code 137|full gc", re.I)),
    ("cpu_pressure", "CPU pressure / throttling",
     re.compile(r"cpu usage (?:[89]\d|100)%|cpu throttl|throttling|load average", re.I)),
    ("restart_crash", "Restarts / crashes",
     re.compile(r"crashloopbackoff|back-off restarting|container restarted|restart(?:_| )count|"
                r"exited with code|liveness probe failed|was killed|terminated", re.I)),
    ("config_error", "Configuration errors",
     re.compile(r"configmap[^\n]{0,60}not found|missing (?:required )?(?:env|environment|config|property)|"
                r"failed to load config|configuration error|could not resolve placeholder|"
                r"required (?:key|property|setting)[^\n]{0,40}(?:missing|not set)|createcontainerconfigerror", re.I)),
    ("startup_failure", "Startup failures",
     re.compile(r"failed to start|startup failed|application run failed|readiness probe failed|"
                r"shutting down due to", re.I)),
]
PATTERN_LABELS = {pid: label for pid, label, _ in PATTERNS}

# Stack-trace frames (Java "at ...", "Caused by:", Python tracebacks).
STACK_RE = re.compile(r"^\s+at [\w$.<>]+\(|^\s*Caused by:|^Traceback \(most recent call last\)|^\s+File \".+\", line \d+")
# Change events that often matter for a timeline (deployments, jobs, config reloads). NOT failure patterns.
CHANGE_EVENT_RE = re.compile(r"scheduler started|sync started|deploy|rollout|config(?:uration)? reload|"
                             r"pulling image|started \w+application|flag \S+ changed|feature[- ]flag", re.I)


def match_patterns(text: str) -> list[str]:
    return [pid for pid, _, rx in PATTERNS if rx.search(text)]


def pattern_hits(lines: list["LogLine"]) -> list[dict[str, Any]]:
    hits_out: list[dict[str, Any]] = []
    for pid, label, _ in PATTERNS:
        hits = [l for l in lines if pid in l.patterns]
        if hits:
            hits_out.append({
                "id": pid, "label": label, "count": len(hits),
                "first_seen": next((h.timestamp for h in hits if h.timestamp), None),
                "first_line": hits[0].number,
                "examples": [f"L{h.number}: {h.text}" for h in hits[:3]],
            })
    hits_out.sort(key=lambda p: p["count"], reverse=True)
    return hits_out


def stack_traces(lines: list["LogLine"]) -> list[dict[str, Any]]:
    """Group consecutive stack-frame lines under the log line they belong to."""
    traces: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    previous: "LogLine | None" = None
    for l in lines:
        if l.is_stack:
            if current is None:
                current = {"line": previous.number if previous else l.number,
                           "header": previous.text if previous else "(no header line)", "frames": []}
                traces.append(current)
            current["frames"].append(f"L{l.number}: {l.text.strip()}")
        else:
            current = None
            previous = l
    return traces


def event_sequence(lines: list["LogLine"], limit: int = 15) -> list[dict[str, Any]]:
    """Chronological 'story': first appearance of each pattern, first error, and change events."""
    events: list[dict[str, Any]] = []
    seen: set[str] = set()
    first_error_done = False
    for l in lines:
        if CHANGE_EVENT_RE.search(l.text) and not l.is_error:
            key = "change:" + re.sub(r"\d+", "#", l.text[25:70])
            if key not in seen:
                seen.add(key)
                events.append({"line": l.number, "timestamp": l.timestamp, "event": "Change / job event",
                               "text": l.text[:200]})
        if l.is_error and not first_error_done:
            first_error_done = True
            events.append({"line": l.number, "timestamp": l.timestamp, "event": "First ERROR", "text": l.text[:200]})
        for pid in l.patterns:
            if pid not in seen:
                seen.add(pid)
                events.append({"line": l.number, "timestamp": l.timestamp,
                               "event": f"First sign of: {PATTERN_LABELS[pid]}", "text": l.text[:200]})
    events.sort(key=lambda e: e["line"])
    return events[:limit]


def suspicious_entries(lines: list["LogLine"], limit: int = 15) -> list[dict[str, Any]]:
    """Lines worth a human's attention, with the reasons they were flagged."""
    out: list[dict[str, Any]] = []
    for l in lines:
        reasons = []
        if l.is_error:
            reasons.append(l.level or "ERROR")
        if l.patterns:
            reasons += [PATTERN_LABELS[p] for p in l.patterns]
        if l.is_warning and not l.patterns:
            continue                      # plain warnings without a known pattern are noise here
        if reasons:
            out.append({"line": l.number, "text": l.text[:300], "reasons": reasons})
    return out[:limit]


def search(lines: list["LogLine"], query: str, max_results: int = 15) -> dict[str, Any]:
    """Find lines matching a known pattern id or a plain keyword (case-insensitive)."""
    query = query.strip()
    if query in PATTERN_LABELS:
        matches = [l for l in lines if query in l.patterns]
        label = PATTERN_LABELS[query]
    else:
        q = query.lower()
        matches = [l for l in lines if q in l.text.lower()]
        label = f"keyword '{query}'"
    return {"query": query, "label": label, "match_count": len(matches),
            "lines": [f"L{l.number}: {l.text}" for l in matches[:max_results]],
            "truncated": len(matches) > max_results}
