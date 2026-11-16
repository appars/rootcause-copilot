"""Deterministic log analysis.

The LLM is good at explaining, but counting and pattern-matching should be
done by plain code: it is fast, repeatable and never invents numbers. Every
figure shown in the UI comes from this module, not from the model.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?)")
LEVEL_RE = re.compile(r"\b(TRACE|DEBUG|INFO|WARN|WARNING|ERROR|FATAL|CRITICAL)\b")
SERVICE_RE = re.compile(r"\[([a-z][a-z0-9\-]{2,40})\]|\bservice=([A-Za-z0-9_\-]+)")
EXCEPTION_RE = re.compile(r"\b((?:[a-z]+\.)*[A-Z][A-Za-z]+(?:Exception|Error))\b")
HTTP_RE = re.compile(r"\b(?:status|http_status|HTTP/\d\.\d)[=: ]+([1-5]\d{2})\b", re.IGNORECASE)

# Pattern catalogue lives in the Error Pattern Analyzer; re-exported here for compatibility.
from tools import error_pattern_analyzer as epa  # noqa: E402
from tools.error_pattern_analyzer import PATTERN_LABELS, PATTERNS  # noqa: E402

__all__ = ["PATTERNS", "PATTERN_LABELS", "LogLine", "parse_lines", "analyze_logs", "search_error_patterns",
           "summarize_for_display"]


@dataclass
class LogLine:
    number: int
    text: str
    timestamp: str | None = None
    level: str | None = None
    service: str | None = None
    patterns: list[str] = field(default_factory=list)
    is_stack: bool = False          # stack-trace frame (attached to the previous line)

    @property
    def is_error(self) -> bool:
        return self.level in ("ERROR", "FATAL", "CRITICAL")

    @property
    def is_warning(self) -> bool:
        return self.level in ("WARN", "WARNING")


def parse_lines(text: str) -> list[LogLine]:
    lines: list[LogLine] = []
    for i, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip()
        if not line.strip():
            continue
        if epa.STACK_RE.search(line):
            lines.append(LogLine(number=i, text=line[:500], is_stack=True))
            continue
        ts = TS_RE.search(line)
        lvl = LEVEL_RE.search(line)
        svc = SERVICE_RE.search(line)
        level = lvl.group(1) if lvl else None
        if level == "WARNING":
            level = "WARN"
        lines.append(LogLine(
            number=i,
            text=line[:500],
            timestamp=ts.group(1) if ts else None,
            level=level,
            service=(svc.group(1) or svc.group(2)) if svc else None,
            patterns=epa.match_patterns(line),
        ))
    return lines


def _normalise(message: str) -> str:
    """Turn 'took 5120ms id=ab12' into 'took #ms id=#' so repeats can be counted."""
    msg = TS_RE.sub("", message)
    msg = re.sub(r"\b[0-9a-f]{8,}\b", "#", msg, flags=re.I)
    msg = re.sub(r"\d+", "#", msg)
    return re.sub(r"\s+", " ", msg).strip()


def analyze_logs(text: str, focus_pattern: str | None = None) -> dict[str, Any]:
    """Analyse raw log text and return only facts found in the text."""
    lines = parse_lines(text)
    level_counts = Counter(l.level for l in lines if l.level)
    timestamps = [l.timestamp for l in lines if l.timestamp]
    services = Counter(l.service for l in lines if l.service)
    exceptions: Counter[str] = Counter()
    http_codes: Counter[str] = Counter()
    for l in lines:
        exceptions.update(set(EXCEPTION_RE.findall(l.text)))
        http_codes.update(HTTP_RE.findall(l.text))

    pattern_hits = epa.pattern_hits(lines)

    repeated = Counter(_normalise(l.text) for l in lines if l.is_error or l.is_warning)
    repeated_msgs = [{"message": m[:200], "count": c} for m, c in repeated.most_common(5) if c > 1]

    important = [l for l in lines if l.is_error or (l.patterns and not l.level == "DEBUG")]
    if focus_pattern:
        important = [l for l in important if focus_pattern in l.patterns] or important
    representative = [f"L{l.number}: {l.text}" for l in important[:12]]

    traces = epa.stack_traces(lines)
    return {
        "total_lines": len(lines),
        "lines_with_timestamp": len(timestamps),
        "time_range": {"start": min(timestamps), "end": max(timestamps)} if timestamps else None,
        "level_counts": dict(level_counts),
        "error_count": sum(1 for l in lines if l.is_error),
        "warning_count": sum(1 for l in lines if l.is_warning),
        "services": dict(services.most_common(6)),
        "exceptions": dict(exceptions.most_common(6)),
        "http_status_codes": dict(http_codes.most_common(6)),
        "patterns": pattern_hits,
        "repeated_messages": repeated_msgs,
        "representative_lines": representative,
        "stack_traces": traces[:5],
        "stack_trace_count": len(traces),
        "event_sequence": epa.event_sequence(lines),
        "suspicious_entries": epa.suspicious_entries(lines),
    }


def search_error_patterns(text: str, query: str, max_results: int = 15) -> dict[str, Any]:
    """Error Pattern Analyzer tool: lines matching a known pattern id or a keyword."""
    return epa.search(parse_lines(text), query, max_results)


def summarize_for_display(analysis: dict[str, Any]) -> str:
    """One-line human summary built only from computed numbers."""
    tr = analysis.get("time_range")
    window = f" between {tr['start']} and {tr['end']}" if tr else ""
    top = ", ".join(f"{p['label']} ({p['count']})" for p in analysis["patterns"][:3]) or "no known patterns"
    traces = f" {analysis['stack_trace_count']} stack trace(s)." if analysis.get("stack_trace_count") else ""
    return (f"{analysis['total_lines']} lines{window}: {analysis['error_count']} errors, "
            f"{analysis['warning_count']} warnings. Top patterns: {top}.{traces}")
