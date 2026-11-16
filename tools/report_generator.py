"""Investigation report generation (Markdown + PDF).

Reports clearly separate OBSERVED FACTS (computed by tools) from the
HYPOTHESIS (model or demo output) and RECOMMENDATIONS. Secret values never
appear because the Kubernetes analyzer masks them before they reach here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import config


def _bullets(items: list[Any] | None, empty: str = "_None recorded._") -> str:
    items = [str(i) for i in (items or []) if str(i).strip()]
    return "\n".join(f"- {i}" for i in items) if items else empty


def generate_markdown_report(incident: dict[str, Any], result: dict[str, Any] | None,
                             timeline: list[dict[str, Any]], audit: list[dict[str, Any]]) -> str:
    """Build the investigation report. Never contains API keys; Secret values are already masked upstream."""
    r = result or {}
    mode = r.get("mode", incident.get("mode", ""))
    final = r.get("final") or {}
    hyp = r.get("hypothesis") or {}
    rem = r.get("remediation") or {}
    ev = r.get("evidence") or {}
    log = ev.get("log_analysis")
    yaml_res = ev.get("yaml_analysis")
    similar = ev.get("similar_incidents") or []
    kb = ev.get("kb_results") or []
    refl = r.get("reflection") or {}
    ea = final.get("evidence_assessment") or {}
    is_demo = mode == config.MODE_DEMO
    hyp_origin = {"demo": "SIMULATED DEMO RESULT (predefined - no AI reasoning)",
                  "rules": "Rule-based heuristic in Demo Mode (no AI reasoning)",
                  "llm": f"Live AI - {config.LLM_MODEL} via {config.LLM_PROVIDER}"}.get(hyp.get("source", ""), "-")
    approval_status = next((a["decision"] for a in reversed(audit)), "no decision recorded")

    lines = [
        f"# Investigation Report - {incident['id']}: {incident['title']}",
        "",
        f"_{config.APP_FULL_NAME} {config.APP_RELEASE}_",
        "",
        "> **Educational, simulated environment.** RootCause Copilot does not connect to production systems. "
        "Any remediation shown was simulated only; nothing was executed.",
        "",
    ]
    if is_demo:
        lines += [f"> **{config.DEMO_LABEL}.** Root-cause conclusions in this report were NOT produced by live AI. "
                  "Log, YAML, memory and document analysis did run for real.", ""]
    lines += [
        "## 1. Incident summary", "",
        f"{final.get('hypothesis') and 'Probable cause (hypothesis): ' + final['hypothesis'] or 'No hypothesis was produced.'}",
        "",
        "## 2. Incident metadata", "",
        "| Field | Value |", "|---|---|",
        f"| Incident ID | {incident['id']} |",
        f"| Service | {incident['service']} |",
        f"| Severity | {incident['severity']} |",
        f"| Status | {incident['status']} |",
        f"| Trigger | {(r.get('trigger') or {}).get('type', 'manual')}"
        + (" (SIMULATED alert)" if (r.get('trigger') or {}).get('type') == "simulated_alert" else "") + " |",
        f"| Investigation mode | {mode} |",
        f"| Created (UTC) | {incident['created_at']} |",
        "",
        "## 3. Symptoms", "",
        incident.get("description") or "_No description provided._",
        "",
        _bullets([p["label"] + f" ({p['count']} log lines)" for p in (log or {}).get("patterns", [])], ""),
        "",
        "## 4. Log analysis findings (deterministic tools - observed facts)", "",
    ]
    if log:
        tr = log.get("time_range")
        lines += [
            f"- Log lines analysed: **{log['total_lines']}**; errors: **{log['error_count']}**; warnings: **{log['warning_count']}**"
            + (f"; stack traces: **{log.get('stack_trace_count', 0)}**" if log.get("stack_trace_count") else ""),
            f"- Time range in logs: {tr['start']} to {tr['end']}" if tr else "- Time range: no timestamps found",
            "", "Chronological sequence:", "",
            _bullets([f"L{e['line']} ({(e['timestamp'] or '-')[11:19]}): {e['event']}" for e in log.get("event_sequence", [])]),
            "", "Representative evidence lines:", "", "```text",
            *log.get("representative_lines", [])[:10], "```", "",
        ]
    else:
        lines += ["_No log file was provided or analysed._", ""]
    lines += ["## 5. Historical incident references (persistent memory)", "",
              _bullets([f"{s['id']} - {s['title']} (similarity {s['score']}; matched on {', '.join(s['matched_on'][:5])}): "
                        f"root cause: {s['root_cause']}" for s in similar], "_No similar past incident was retrieved._"),
              "", "Knowledge-base references (passed the relevance filter):", "",
              _bullets([f"{k['filename']} (chunk {k['chunk']}): matched {', '.join(k['matched_terms'])}" for k in kb],
                       "_No relevant document._"),
              "", "## 6. Kubernetes findings (deterministic validation)", ""]
    if yaml_res:
        lines += [_bullets([f"[{f['severity']}] {f['resource']}: {f['message']} Evidence: {f.get('evidence', '-')}. "
                            f"Recommended: {f.get('recommendation', '-')}" for f in yaml_res.get("findings", [])[:12]],
                           "_No issues found by the static checks._"),
                  "", f"_{yaml_res.get('note', '')}_", ""]
    else:
        lines += ["_No Kubernetes YAML was analysed._", ""]
    lines += ["## 7. Root-cause hypothesis", "",
              f"**Source:** {hyp_origin}", "",
              f"**Initial hypothesis:** {hyp.get('hypothesis', '_none_')}", "",
              "**Final hypothesis" + (" (revised after review)" if final.get("revised") else "") +
              f":** {final.get('hypothesis', '_none_')}", "",
              f"**Evidence assessment:** {ea.get('label_text', '-')} - {ea.get('explanation', '')}", "",
              f"**Stated confidence level:** {final.get('confidence', '-')} (qualitative, not a probability)", "",
              "Reflection rounds:", ""]
    for rd in refl.get("rounds", []):
        lines.append(f"- Round {rd['round']}: verdict **{rd['verdict']}** ({rd.get('evidence_label', '-')}). "
                     + "; ".join(rd.get("issues", [])[:3]))
    if not refl.get("rounds"):
        lines.append("_No reflection rounds recorded._")
    lines += ["", "> Reflection reduces mistakes but does not guarantee a correct diagnosis.", "",
              "## 8. Supporting evidence", "",
              _bullets(ea.get("supporting")), "", "Cited by the hypothesis:", "", _bullets(final.get("supporting_evidence")), "",
              "## 9. Contradictory evidence", "",
              _bullets(ea.get("contradictory"), "_None found._"), "",
              "Alternative explanations considered:", "", _bullets(final.get("alternatives")), "",
              "## 10. Missing information", "",
              _bullets(final.get("limitations")), "",
              "## 11. Recommended actions", ""]
    if rem:
        lines += [f"- **Proposed action:** {rem.get('action')} (`{rem.get('action_type')}` on `{rem.get('target')}`)",
                  f"- **Reason:** {rem.get('reason', '-')}",
                  f"- **Risk level:** {rem.get('risk_level', '-')}",
                  f"- **Requires human approval:** {'Yes' if rem.get('requires_approval') else 'No (read-only)'}",
                  f"- **Expected impact:** {rem.get('expected_impact')}",
                  f"- **Potential side effects / risks:** {rem.get('risks')}",
                  f"- **Preconditions:** {rem.get('preconditions')}",
                  f"- **Rollback:** {rem.get('rollback')}", ""]
    else:
        lines += ["_No remediation proposed._", ""]
    lines += ["## 12. Human approval status (simulated workflow)", "",
              f"**Current status:** {approval_status}", "",
              "| Time (UTC) | Decision | Reviewer | Rationale | Execution |", "|---|---|---|---|---|"]
    for a in audit:
        lines.append(f"| {a['ts']} | {a['decision']} | {a.get('reviewer') or '-'} | "
                     f"{(a.get('rationale') or '-').replace('|', '/')} | {(a.get('execution') or '-').replace('|', '/')} |")
    if not audit:
        lines.append("| - | no decisions yet | - | - | - |")
    lines += ["", "## 13. Investigation timeline (execution trace)", "",
              "| Step | Status | Started (UTC) | Duration | Origin |", "|---|---|---|---|---|"]
    for t in r.get("trace") or []:
        dur = t.get("duration_ms")
        lines.append(f"| {t['step']} | {t['status']} | {(t.get('started_at') or '-')[11:23] or '-'} | "
                     f"{f'{dur:.1f} ms' if isinstance(dur, (int, float)) else '-'} | {t.get('origin') or '-'} |")
    lines += ["", "Event log:", "", "| Time (UTC) | Stage | Event | Status |", "|---|---|---|---|"]
    for t in timeline:
        sim = " (SIMULATED)" if t.get("simulated") else ""
        lines.append(f"| {t['ts']} | {t['stage']} | {t['message'].replace('|', '/')}{sim} | {t['status']} |")
    lines += ["", "## 14. Investigation mode", "",
              f"{mode}" + (f" - {config.DEMO_LABEL}." if is_demo else
                           f" - {r.get('llm_calls', 0)} API call(s) to {config.LLM_PROVIDER} `{config.LLM_MODEL}`."), "",
              "Resolution recorded by the engineer:", "",
              f"- **Root cause (confirmed):** {incident.get('root_cause') or '_not yet confirmed_'}",
              f"- **Resolution:** {incident.get('resolution') or '_not yet recorded_'}",
              f"- **Lessons learned:** {incident.get('lessons_learned') or '_not yet recorded_'}", "",
              "## 15. Report generation", "",
              f"Generated at {datetime.now(timezone.utc).replace(microsecond=0).isoformat()} by "
              f"{config.APP_NAME} {config.APP_RELEASE} (build {config.APP_VERSION}).", "",
              "---", "_Diagnoses are hypotheses for a human engineer to verify; they are not guaranteed to be correct._"]
    return "\n".join(lines)


def _latin1(text: str) -> str:
    """Core PDF fonts only support Latin-1; replace common Unicode punctuation."""
    table = {"–": "-", "—": "-", "‘": "'", "’": "'", "“": '"', "”": '"',
             "→": "->", "…": "...", "•": "-", "≥": ">=", "≤": "<="}
    for k, v in table.items():
        text = text.replace(k, v)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def markdown_to_pdf(markdown: str) -> bytes:
    """Render the Markdown report as a simple, readable PDF (headings + wrapped text)."""
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    width = pdf.w - pdf.l_margin - pdf.r_margin
    in_code = False
    for raw in markdown.splitlines():
        line = _latin1(raw)
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            pdf.set_font("Courier", size=7)
            pdf.multi_cell(width, 3.6, line[:160], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            continue
        if line.startswith("# "):
            pdf.set_font("Helvetica", "B", 15)
            pdf.multi_cell(width, 8, line[2:], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        elif line.startswith("## "):
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 12)
            pdf.multi_cell(width, 7, line[3:], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        elif line.startswith("|---"):
            continue
        elif line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            pdf.set_font("Helvetica", size=8)
            pdf.multi_cell(width, 4.5, "  |  ".join(cells), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        elif not line.strip():
            pdf.ln(2)
        else:
            pdf.set_font("Helvetica", size=9.5)
            pdf.multi_cell(width, 5, line.replace("**", "").replace("`", "").lstrip("> "),
                           new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    return bytes(pdf.output())
