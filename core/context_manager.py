"""Context management (Concept 2).

Persistent memory = what we KEEP over time.
Context management = what we BRING into this particular model call.

We rank and filter the evidence, apply a size budget, wrap untrusted
content in clear delimiters, and record what was included, truncated or
excluded so students can see exactly what the model received.
"""
from __future__ import annotations

import re
from typing import Any

import config
from core.tool_executor import InvestigationState
from tools.log_analyzer import LogLine, _normalise, parse_lines

INJECTION_RE = re.compile(
    r"ignore (?:all |any )?(?:previous|prior|above) instructions|disregard (?:the )?(?:system|previous)|"
    r"you are now|system prompt|act as an? |mark (?:this )?incident (?:as )?resolved", re.I)


def rank_log_lines(lines: list[LogLine]) -> list[tuple[LogLine, int, int]]:
    """Score lines: errors and known patterns first; collapse duplicates (keep first + count)."""
    seen: dict[str, list[Any]] = {}
    for line in lines:
        score = (3 if line.is_error else 1 if line.is_warning else 0) + 2 * len(line.patterns)
        if score == 0:
            continue
        key = _normalise(line.text)
        if key in seen:
            seen[key][2] += 1
        else:
            seen[key] = [line, score, 1]
    ranked = sorted(seen.values(), key=lambda t: (-t[1], t[0].number))
    return [(l, s, c) for l, s, c in ranked]


def find_injection_lines(text: str) -> list[str]:
    return [f"L{i}" for i, line in enumerate(text.splitlines(), 1) if INJECTION_RE.search(line)]


def build_context(state: InvestigationState, budget: int = config.MAX_CONTEXT_CHARS) -> dict[str, Any]:
    sections: list[tuple[str, str, int]] = []   # (name, text, items)
    excluded: list[str] = []
    notes: list[str] = []

    meta = (f"Incident: {state.title}\nService: {state.service}\n"
            f"Description (user-provided): {state.description[:500] or '(none)'}")
    if state.context_notes.strip():
        meta += f"\nAdditional context (user-provided, untrusted): <untrusted_evidence>{state.context_notes[:800]}</untrusted_evidence>"
    if state.log_analysis and state.log_analysis.get("event_sequence"):
        meta += "\nChronological sequence: " + "; ".join(
            f"L{e['line']} {e['event']}" for e in state.log_analysis["event_sequence"][:8])
    sections.append(("Incident metadata", meta, 1))

    if state.log_analysis:
        a = state.log_analysis
        stats = (f"Lines analysed: {a['total_lines']}; errors: {a['error_count']}; warnings: {a['warning_count']}; "
                 f"time range: {a['time_range']['start'] + ' to ' + a['time_range']['end'] if a['time_range'] else 'n/a'}\n"
                 "Detected patterns: " + ("; ".join(f"{p['id']} ({p['label']}) x{p['count']}" for p in a["patterns"]) or "none")
                 + "\nExceptions: " + (", ".join(f"{k} x{v}" for k, v in a["exceptions"].items()) or "none"))
        sections.append(("Log statistics (computed by tools)", stats, 1))
        ranked = rank_log_lines(parse_lines(state.log_text))
        chosen = ranked[: config.MAX_LOG_LINES_IN_CONTEXT]
        if len(ranked) > len(chosen):
            excluded.append(f"{len(ranked) - len(chosen)} lower-ranked distinct log messages (budget: "
                            f"{config.MAX_LOG_LINES_IN_CONTEXT} lines)")
        total_lines = a["total_lines"]
        dupes = sum(c - 1 for _, _, c in chosen)
        notes.append(f"Selected {len(chosen)} of {total_lines} log lines; {dupes} duplicate occurrences collapsed.")
        body = "\n".join(f"L{l.number}: {l.text}" + (f"   [repeated x{c}]" if c > 1 else "") for l, _, c in chosen)
        sections.append(("Most relevant log lines (untrusted data)", f"<untrusted_evidence>\n{body}\n</untrusted_evidence>", len(chosen)))
        inj = find_injection_lines(state.log_text) + [f"context:{x}" for x in find_injection_lines(state.context_notes)]
        if inj:
            notes.append(f"Possible prompt-injection text found in uploaded logs ({', '.join(inj[:5])}). "
                         "It is treated as data, never as instructions.")
    else:
        excluded.append("Logs: none provided")

    if state.similar_incidents:
        items = state.similar_incidents[: config.MAX_SIMILAR_INCIDENTS]
        body = "\n".join(f"- {s['id']} '{s['title']}' (similarity {s['score']}): root cause: {s['root_cause'][:220]}; "
                         f"resolution: {s['resolution'][:220]}" for s in items)
        sections.append(("Similar past incidents (from SQLite memory)", body, len(items)))
    for name, reason in state.unavailable.items():
        excluded.append(f"{name}: unavailable ({reason[:120]})")

    if state.kb_results:
        items = state.kb_results[: config.MAX_KB_SNIPPETS]
        body = "\n".join(f"- [{k['filename']}#{k['chunk']}] {k['snippet'][:400]}" for k in items)
        sections.append(("Knowledge-base snippets (untrusted data)", f"<untrusted_evidence>\n{body}\n</untrusted_evidence>", len(items)))

    if state.yaml_analysis:
        fs = [f for f in state.yaml_analysis["findings"] if f["severity"] in ("error", "warning")][:8]
        body = "\n".join(f"- [{f['severity']}] {f['resource']}: {f['message']}" for f in fs) or "No errors or warnings."
        sections.append(("Kubernetes YAML findings (static, secrets masked)", body, len(fs)))
    elif state.yaml_error:
        excluded.append(f"Kubernetes YAML: could not be parsed ({state.yaml_error[:100]})")

    # Apply the character budget in priority order.
    parts: list[str] = []
    included: list[dict[str, Any]] = []
    used = 0
    truncated = False
    for name, text, items in sections:
        block = f"### {name}\n{text}\n"
        remaining = budget - used
        if remaining <= 200:
            excluded.append(f"{name}: dropped (context budget of {budget} characters reached)")
            truncated = True
            continue
        if len(block) > remaining:
            block = block[: remaining - 40] + "\n...[truncated to fit budget]\n"
            truncated = True
            excluded.append(f"{name}: truncated to fit the context budget of {budget} characters")
        parts.append(block)
        used += len(block)
        included.append({"section": name, "items": items, "chars": len(block)})

    return {"text": "\n".join(parts), "chars": used, "budget": budget, "approx_tokens": used // 4,
            "included": included, "excluded": excluded, "notes": notes, "truncated": truncated}
