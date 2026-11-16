"""New Investigation page: start (alert / sample / manual) and inspect results."""
from __future__ import annotations

import json
from typing import Any

import streamlit as st

import config
from core import approval
from core.event_handler import SIMULATED_ALERTS, handle_alert, load_scenarios, scenario_input, simulate_alert
from core.llm_client import LLMError
from core.orchestrator import refresh_report, run_investigation
from core.schemas import IncidentInput
from core.tool_executor import FAILURE_MODES
from memory import audit_repository, incident_repository
from memory.database import DatabaseError
from tools.report_generator import markdown_to_pdf
from core.trace import STATUS_ICONS
from memory.document_repository import list_documents
from tools.uploads import UploadError, decode_text, sanitize_filename, validate_upload
from ui.common import (friendly_llm_error, get_llm, is_live, masked_key, mode_banner, offer_demo_mode,
                       render_timeline, render_trace, severity_badge, status_badge)

EVIDENCE_COLORS = {"strong": "#047857", "partial": "#b45309", "contradictory": "#b91c1c", "insufficient": "#475569"}


# ----------------------------------------------------------------- start
def _run(inp: IncidentInput) -> None:
    llm = None
    if is_live():
        llm = get_llm()
        if llm is None:
            st.error("Live AI Mode needs a Groq API key - connect it in the sidebar, or switch to Demo Mode.")
            return
    label = ("Live AI Mode: the agent is calling Groq and running tools..." if llm else
             "Demo Mode: running deterministic tools (AI conclusions are predefined)...")
    try:
        with st.status(label, expanded=True) as box:
            live_view = st.empty()

            def on_trace(steps: list[dict[str, Any]]) -> None:   # live, real progress of the agent
                live_view.markdown("\n".join(
                    f"- {STATUS_ICONS.get(s['status'], '•')} **{s['step']}** - {s['status']}"
                    + (f" · {s['duration_ms']:.0f} ms" if isinstance(s.get('duration_ms'), (int, float)) else "")
                    for s in steps if s["status"] != "Pending"))

            result = run_investigation(inp, st.session_state["mode"], llm,
                                       failure_mode=st.session_state.get("failure_mode", "none"), on_trace=on_trace)
            box.update(label=f"Investigation {result['incident_id']}: {result['status']}",
                       state="complete" if result["status"] == "completed" else "error", expanded=False)
    except LLMError as e:
        friendly_llm_error(e)
        return
    except (ValueError, DatabaseError) as e:
        st.error(str(e))
        return
    st.session_state["current_incident_id"] = result["incident_id"]
    if result["status"] == "completed":
        st.success(f"Investigation {result['incident_id']} completed. Review the results below.")


def _start_section() -> None:
    st.subheader("Start an investigation")
    t_alert, t_sample, t_manual = st.tabs(["🚨 Simulated alert", "📦 Sample incident library", "✍️ Manual"])
    scenarios = load_scenarios()

    with t_alert:
        st.markdown("**Concept 4 - event-driven execution.** A **SIMULATED** monitoring alert *starts* the agent - "
                    "nobody types a prompt. RootCause Copilot is **not** connected to real monitoring (no Prometheus). "
                    "Duplicate alerts for an open incident are suppressed.")
        sid = st.selectbox("Alert to simulate", list(SIMULATED_ALERTS),
                           format_func=lambda k: f"{SIMULATED_ALERTS[k]['alertname']} ({SIMULATED_ALERTS[k]['service']})",
                           key="alert_choice")
        if st.button("🚨 Simulate New Incident Alert", type="primary"):
            alert = simulate_alert(sid)
            with st.expander("Simulated alert payload (Alertmanager-style, SIMULATED)"):
                st.json(alert)
            inp, duplicate_of = handle_alert(alert)
            if duplicate_of:
                st.warning(f"Duplicate alert suppressed: incident {duplicate_of} for this alert is still open. "
                           "Close or resolve it first (event de-duplication).")
                st.session_state["current_incident_id"] = duplicate_of
            elif inp:
                _run(inp)

    with t_sample:
        sid = st.selectbox("Synthetic incident (fictional data)", list(scenarios),
                           format_func=lambda k: f"{k} - {scenarios[k]['title']}"
                           + ("  [challenge - no predefined demo result]" if scenarios[k].get("challenge") else ""),
                           key="scenario_choice")
        s = scenarios[sid]
        st.caption(f"{s['service']} · {s['severity']} · log: `{s['log_file']}`"
                   + (f" · YAML: `{s['yaml_file']}`" if s.get("yaml_file") else "") + f"\n\n{s['description']}")
        if st.button("▶ Run sample investigation"):
            _run(scenario_input(sid))

    with t_manual:
        with st.form("manual_form"):
            c1, c2, c3 = st.columns([3, 2, 1])
            title = c1.text_input("Incident title", placeholder="Checkout requests failing")
            service_choice = c2.selectbox("Affected service", config.KNOWN_SERVICES + ["Other (type below)"])
            severity = c3.selectbox("Severity", ["SEV1", "SEV2", "SEV3", "SEV4"], index=1)
            other_service = st.text_input("Other service name (only if 'Other' is selected)", max_chars=60)
            description = st.text_area("Description", placeholder="What are users seeing? Since when?", max_chars=2000)
            context_notes = st.text_area("Optional context", max_chars=1500,
                                         placeholder="Recent changes, deployments, observations, ticket links...")
            log_file = st.file_uploader("Log file (.log / .txt, max 2 MB)", type=["log", "txt"])
            log_paste = st.text_area("...or paste log lines", height=120)
            yaml_file = st.file_uploader("Kubernetes YAML (optional)", type=["yaml", "yml"])
            yaml_paste = st.text_area("...or paste YAML (optional)", height=100)
            submitted = st.form_submit_button("▶ Run investigation", type="primary")
        if submitted:
            try:
                log_text, log_name = log_paste, "pasted text" if log_paste.strip() else ""
                if log_file is not None:
                    data = log_file.getvalue()
                    log_name = sanitize_filename(log_file.name)
                    validate_upload(log_name, data, config.ALLOWED_LOG_EXTENSIONS)
                    log_text = decode_text(log_name, data)
                yaml_text, yaml_name = yaml_paste, "pasted text" if yaml_paste.strip() else ""
                if yaml_file is not None:
                    data = yaml_file.getvalue()
                    yaml_name = sanitize_filename(yaml_file.name)
                    validate_upload(yaml_name, data, config.ALLOWED_YAML_EXTENSIONS)
                    yaml_text = decode_text(yaml_name, data)
                service = other_service.strip() if service_choice.startswith("Other") else service_choice
                if not title.strip() or not service.strip():
                    raise UploadError("Title and service are required.")
                if not log_text.strip() and not description.strip():
                    raise UploadError("Provide at least a description or some log lines - there is nothing to investigate.")
                _run(IncidentInput(title=title, service=service, severity=severity, description=description,
                                   log_text=log_text, log_filename=log_name, yaml_text=yaml_text,
                                   yaml_filename=yaml_name, context_notes=context_notes))
            except UploadError as e:
                st.error(f"Input problem: {e} Your other entries are kept - fix this and submit again.")

    with st.expander("🧪 Instructor controls - simulate a tool failure (Concept 6)"):
        st.session_state["failure_mode"] = st.radio(
            "Knowledge-base tool behaviour for the NEXT investigation", list(FAILURE_MODES),
            format_func=FAILURE_MODES.get, index=list(FAILURE_MODES).index(st.session_state.get("failure_mode", "none")))
        st.caption("Clearly labelled simulation. Watch the trace/timeline for retry, recovery or degraded steps.")


# --------------------------------------------------------------- results
def _evidence_tab(result: dict[str, Any]) -> None:
    ev = result.get("evidence") or {}
    log = ev.get("log_analysis")
    st.caption("Everything on this tab was computed by deterministic tools - these are **observed facts**, not model output.")
    if log:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Log lines", log["total_lines"])
        c2.metric("Errors", log["error_count"])
        c3.metric("Warnings", log["warning_count"])
        tr = log.get("time_range")
        c4.metric("Time window", f"{tr['start'][11:16]}-{tr['end'][11:16]}" if tr else "n/a")
        if log["patterns"]:
            st.markdown("**Detected patterns**")
            st.dataframe([{"Pattern": p["label"], "Lines": p["count"], "First seen": p["first_seen"] or "-",
                           "Example": p["examples"][0]} for p in log["patterns"]], hide_index=True, width="stretch")
        if log["exceptions"]:
            st.markdown("**Exceptions:** " + ", ".join(f"`{k}` x{v}" for k, v in log["exceptions"].items()))
        if log["repeated_messages"]:
            st.markdown("**Repeated messages**")
            st.dataframe(log["repeated_messages"], hide_index=True, width="stretch")
        if log.get("event_sequence"):
            st.markdown("**Chronological sequence** (first appearance of each signal)")
            st.dataframe([{"Line": f"L{e['line']}", "Time": (e["timestamp"] or "-")[11:23], "Event": e["event"],
                           "Source line": e["text"]} for e in log["event_sequence"]], hide_index=True, width="stretch")
        if log.get("stack_trace_count"):
            with st.expander(f"Stack traces detected: {log['stack_trace_count']}"):
                for t in log["stack_traces"]:
                    st.code(f"L{t['line']}: {t['header']}\n" + "\n".join(t["frames"]), language="text")
        if log.get("suspicious_entries"):
            with st.expander(f"Suspicious entries ({len(log['suspicious_entries'])} shown, with reasons)"):
                st.dataframe([{"Line": f"L{x['line']}", "Why flagged": ", ".join(x["reasons"]), "Source line": x["text"]}
                              for x in log["suspicious_entries"]], hide_index=True, width="stretch")
        with st.expander("Representative evidence lines"):
            st.code("\n".join(log["representative_lines"]) or "(none)", language="text")
        for search in ev.get("pattern_searches", []):
            with st.expander(f"Pattern search: {search['label']} ({search['match_count']} matches)"):
                st.code("\n".join(search["lines"]) or "(no matches)", language="text")
    else:
        st.info("No log evidence was analysed for this incident.")
    if ev.get("yaml_analysis"):
        y = ev["yaml_analysis"]
        st.markdown("**Kubernetes YAML findings** - *deterministic validation* (static checks; Secret values masked)")
        st.dataframe([{"Severity": f["severity"], "Resource": f["resource"], "Finding": f["message"],
                       "Evidence": f.get("evidence", "-"), "Recommended correction": f.get("recommendation", "-")}
                      for f in y["findings"]], hide_index=True, width="stretch")
        st.caption(y["note"])
    elif ev.get("yaml_error"):
        st.warning(f"Kubernetes YAML could not be parsed: {ev['yaml_error']}")
    if ev.get("kb_results"):
        st.markdown("**Knowledge-base matches** (only documents that passed the relevance filter)")
        for k in ev["kb_results"]:
            with st.expander(f"{k['filename']} (chunk {k['chunk']}, score {k['score']})"):
                st.text(k["snippet"])
    for tool, reason in (ev.get("unavailable_tools") or {}).items():
        st.warning(f"`{tool}` was unavailable, so its evidence is missing: {reason}")


def _context_tab(result: dict[str, Any]) -> None:
    ctx = result.get("context")
    if not ctx:
        st.info("No context was built.")
        return
    st.markdown("**Concept 2 - context management.** Not everything is sent to the model: evidence is ranked, "
                "duplicates are collapsed and a size budget is enforced.")
    st.progress(min(1.0, ctx["chars"] / ctx["budget"]),
                text=f"{ctx['chars']} / {ctx['budget']} characters (~{ctx['approx_tokens']} tokens)")
    st.dataframe(ctx["included"], hide_index=True, width="stretch")
    for n in ctx["notes"]:
        st.caption("ℹ️ " + n)
    if ctx["excluded"]:
        st.markdown("**Excluded / truncated:**\n" + "\n".join(f"- {x}" for x in ctx["excluded"]))
    with st.expander("Exact context text"):
        if result["mode"] == config.MODE_DEMO:
            st.caption("Demo Mode: this context was assembled to show the technique but was NOT sent to any LLM.")
        st.code(ctx["text"], language="text")
    _memory_layers(result)


def _memory_layers(result: dict[str, Any]) -> None:
    """Make the three kinds of 'memory' visible side by side."""
    st.markdown("#### Three kinds of memory in this investigation")
    ev = result.get("evidence") or {}
    counts = incident_repository.incident_counts()
    c1, c2, c3 = st.columns(3)
    with c1.container(border=True):
        st.markdown("**Short-term context** · `st.session_state`")
        st.caption("Lives only in this browser session; lost on refresh/restart.")
        st.markdown(f"- Mode: {st.session_state.get('mode')}\n- API key: {masked_key()}\n"
                    f"- Selected investigation: {st.session_state.get('current_incident_id')}")
    with c2.container(border=True):
        st.markdown("**Persistent incident memory** · SQLite")
        st.caption("On disk; survives restarts (and pod restarts with a PVC).")
        st.markdown(f"- Incidents stored: {counts['memory_records']}\n- This incident: {result['incident_id']}\n"
                    f"- Database: `{config.DB_PATH.name}`")
    with c3.container(border=True):
        st.markdown("**Retrieved knowledge** · used for THIS incident")
        st.caption("Selected from memory and documents, then placed in the context.")
        sims = [s["id"] for s in ev.get("similar_incidents") or []]
        kbs = [k["filename"] for k in ev.get("kb_results") or []]
        st.markdown(f"- Similar incidents: {', '.join(sims) or 'none'}\n- Documents: {', '.join(kbs) or 'none'}")


def _actions_tab(result: dict[str, Any]) -> None:
    calls = result.get("tool_calls") or []
    st.markdown(f"**Concept 3 - dynamic decision-making.** The agent chose each next tool based on the evidence so far. "
                f"Limits: max {config.MAX_TOOL_CALLS} tool calls, allowlisted tools only, arguments validated first.")
    if not calls:
        st.info("No tools were executed.")
        return
    st.dataframe([{"#": i + 1, "Tool": c["tool"], "Selected by": c["selected_by"], "Why": c["reason"],
                   "Arguments": json.dumps(c["arguments"]), "Status": c["status"], "Attempts": c["attempts"],
                   "Result": c["summary"]} for i, c in enumerate(calls)], hide_index=True, width="stretch")
    st.caption("Only short action summaries are shown - hidden model reasoning is never displayed.")


def _similar_tab(result: dict[str, Any]) -> None:
    sims = (result.get("evidence") or {}).get("similar_incidents") or []
    st.markdown("**Concept 1 - persistent memory.** Retrieved from SQLite incident history (it survives restarts).")
    if not sims:
        st.info("No sufficiently similar past incidents were found (or retrieval was not run).")
    for s in sims:
        with st.container(border=True):
            st.markdown(f"**{s['id']}** - {s['title']} · `{s['service']}` · similarity **{s['score']}**")
            st.markdown(f"Root cause: {s['root_cause']}\n\nResolution: {s['resolution']}")
            st.caption("Matched on: " + ", ".join(s["matched_on"]))


def _diagnosis_tab(result: dict[str, Any]) -> None:
    hyp, final, refl = result.get("hypothesis"), result.get("final"), result.get("reflection") or {}
    if not hyp:
        st.info("No diagnosis was produced (see timeline).")
        return
    src = {"demo": "SIMULATED DEMO RESULT - predefined, no AI reasoning",
           "rules": "Demo Mode - rule-based heuristic, no AI reasoning",
           "llm": f"Live AI - generated by {config.LLM_MODEL}"}.get(hyp["source"], hyp["source"])
    if hyp["source"] in ("demo", "rules"):
        st.warning(f"**{config.DEMO_LABEL}.** The hypothesis below was not produced by live AI.")
    st.markdown(f"**Initial hypothesis** <span class='rc-muted'>({src})</span>", unsafe_allow_html=True)
    st.write(hyp["hypothesis"])
    st.caption(f"Category: {hyp['root_cause_category']} · stated confidence: {hyp['confidence']}")
    st.markdown("**Concept 5 - self-reflection** (max 2 rounds)")
    for rd in refl.get("rounds", []):
        with st.expander(f"Review round {rd['round']}: verdict '{rd['verdict']}' - {rd.get('evidence_label', '')} "
                         f"({', '.join(rd['reviewers'])})",
                         expanded=rd["verdict"] != "supported"):
            st.dataframe([{"Check": c["check"], "Passed": "✅" if c["passed"] else "❌", "Detail": c["detail"]}
                          for c in rd["checks"]], hide_index=True, width="stretch")
            for i in rd["issues"]:
                st.markdown(f"- {i}")
    st.caption(refl.get("note", ""))
    if final:
        with st.container(border=True):
            st.markdown("**Final hypothesis**" + (" (revised after review)" if final.get("revised") else ""))
            st.write(final["hypothesis"])
            ea = final.get("evidence_assessment") or {}
            if ea:
                st.markdown(f"<span class='rc-badge' style='background:{EVIDENCE_COLORS[ea['label']]}'>"
                            f"{ea['label_text']}</span> <span class='rc-muted'>{ea['explanation']}</span>",
                            unsafe_allow_html=True)
            st.caption(f"Stated confidence level: {final['confidence']} (a qualitative level, not a probability)")
            c1, c2 = st.columns(2)
            c1.markdown("**Supporting evidence (verified by tools)**\n" +
                        ("\n".join(f"- {e}" for e in ea.get("supporting", [])) or "- none"))
            c1.markdown("**Evidence cited in the hypothesis**\n" +
                        ("\n".join(f"- {e}" for e in final["supporting_evidence"]) or "- none"))
            c2.markdown("**Contradictory evidence**\n" +
                        ("\n".join(f"- {e}" for e in ea.get("contradictory", [])) or "- none found"))
            c2.markdown("**Alternative explanations**\n" + ("\n".join(f"- {a}" for a in final["alternatives"]) or "- none"))
            st.markdown("**Missing information / limitations**\n" + "\n".join(f"- {l}" for l in final["limitations"]))
        st.caption("A hypothesis is not a confirmed root cause. An engineer must verify it.")


def _approval_tab(inc: dict[str, Any], result: dict[str, Any]) -> None:
    rem = result.get("remediation")
    st.markdown("**Concept 7 - human approval.** The agent recommends; an authorised human decides. "
                "Approval triggers a **SIMULATED** action only - nothing is executed.")
    if not rem:
        st.info("No remediation was proposed.")
        return
    with st.container(border=True):
        st.markdown(f"**Proposed action:** {rem['action']}")
        st.markdown(f"Type: `{rem['action_type']}` · Target: `{rem['target']}` · "
                    f"Risk level: **{rem.get('risk_level', 'High')}** · "
                    f"Requires approval: **{'YES' if rem['requires_approval'] else 'no (read-only)'}**")
        st.markdown(f"**Reason for recommendation:** {rem.get('reason', '-')}")
        st.markdown("**Supporting evidence:** " + "; ".join(rem.get("evidence", [])[:3]))
        st.markdown(f"**Expected impact:** {rem['expected_impact']}\n\n**Potential side effects / risks:** {rem['risks']}\n\n"
                    f"**Preconditions:** {rem['preconditions']}\n\n**Rollback:** {rem['rollback']}")
        st.caption("Educational approval workflow: decisions are recorded, but nothing is ever executed.")
    if rem["requires_approval"] and inc["status"] == "awaiting_approval":
        with st.form("approval_form"):
            reviewer = st.text_input("Reviewer name (recorded in the audit trail)")
            rationale = st.text_area("Rationale (required for reject / more information)")
            c1, c2, c3 = st.columns(3)
            approve = c1.form_submit_button("✅ Approve (simulated)", type="primary")
            reject = c2.form_submit_button("❌ Reject")
            more = c3.form_submit_button("❓ Request more information")
        decision = "approve" if approve else "reject" if reject else "more_info" if more else None
        if decision:
            try:
                rec = approval.record_decision(inc["id"], rem, decision, reviewer, rationale)
                refresh_report(inc["id"])
                st.success(f"Decision recorded: {rec['decision']}. {rec.get('execution') or ''}")
                st.rerun()
            except ValueError as e:
                st.error(str(e))
        st.caption("In a real company this button alone is not enough: identity, role-based access control, "
                   "change windows and an immutable audit log are also required.")
    else:
        st.caption(f"Current incident status: {inc['status']}.")
    audit = audit_repository.list_audit_records(inc["id"])
    if audit:
        st.markdown("**Audit trail**")
        st.dataframe([{"Time (UTC)": a["ts"], "Decision": a["decision"], "Reviewer": a["reviewer"] or "-",
                       "Rationale": a["rationale"] or "-", "Execution": a["execution"] or "-"} for a in audit],
                     hide_index=True, width="stretch")


def _close_and_report_tab(inc: dict[str, Any], result: dict[str, Any]) -> None:
    st.markdown("**Save what was learned to persistent memory.** Closing the incident stores the confirmed root cause, "
                "resolution and lessons learned in SQLite, so future investigations can retrieve it.")
    if inc["status"] != "closed":
        final = result.get("final") or {}
        rem = result.get("remediation") or {}
        with st.form("close_form"):
            root_cause = st.text_area("Confirmed root cause", value=inc.get("root_cause") or final.get("hypothesis", ""))
            resolution = st.text_area("Resolution", value=inc.get("resolution") or rem.get("action", ""))
            lessons = st.text_area("Lessons learned", value=inc.get("lessons_learned") or "")
            if st.form_submit_button("💾 Close incident and save to memory"):
                try:
                    approval.close_incident(inc["id"], root_cause, resolution, lessons)
                    refresh_report(inc["id"])
                    st.success("Saved to persistent memory.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
    else:
        st.success("This incident is closed and stored in memory.")
    if st.button("🔄 Regenerate report"):
        refresh_report(inc["id"])
    reports = [r for r in incident_repository.list_reports() if r["incident_id"] == inc["id"]]
    if reports:
        md = incident_repository.get_report(reports[0]["id"])["markdown"]  # type: ignore[index]
        c1, c2 = st.columns(2)
        c1.download_button("⬇ Download Markdown", md, file_name=f"{inc['id']}_report.md", mime="text/markdown")
        c2.download_button("⬇ Download PDF", markdown_to_pdf(md), file_name=f"{inc['id']}_report.pdf",
                           mime="application/pdf")
        with st.expander("Preview report"):
            st.markdown(md)


def render_incident(iid: str) -> None:
    inc = incident_repository.get_incident(iid)
    result = incident_repository.get_result(iid)
    if not inc or not result:
        st.info("Select or start an investigation.")
        return
    st.markdown(f"### {inc['id']} - {inc['title']}")
    trig = (result.get("trigger") or {}).get("type", "manual")
    st.markdown(severity_badge(inc["severity"]) + status_badge(inc["status"]) +
                f"<span class='rc-muted'>{inc['service']} · {result['mode']} · trigger: {trig}"
                + (" (SIMULATED)" if trig == "simulated_alert" else "") + "</span>", unsafe_allow_html=True)
    if result["mode"] == config.MODE_DEMO:
        st.caption(f"🔶 {config.DEMO_LABEL}. Tools (log, YAML, memory, documents) really ran.")
    else:
        st.caption(f"🟢 Live AI Mode - {result.get('llm_calls', 0)} API call(s) to {config.LLM_PROVIDER} `{config.LLM_MODEL}`.")
    for e in result.get("errors", []):
        st.error(f"{e['kind']}: {e['message']}")
    if result.get("status") == "stopped":
        st.info("Live AI was unavailable, so the investigation stopped. Evidence collected so far is saved. "
                "Retry later, fix the key in the sidebar, or continue in Demo Mode and run it again.")
        offer_demo_mode(f"demo_offer_{iid}")
    sims = (result.get("evidence") or {}).get("similar_incidents") or []
    if sims:
        st.success("🧠 **Memory:** retrieved " + ", ".join(
            f"**{s['id']}** (similarity {s['score']}; matched on {', '.join(s['matched_on'][:4])})" for s in sims[:3])
            + " from persistent SQLite memory.")
    tabs = st.tabs(["Execution trace", "Evidence", "Context & memory", "Agent actions", "Similar incidents",
                    "Diagnosis & evidence", "Approval", "Close & report", "Event log"])
    with tabs[0]:
        st.markdown("What the agent **actually** did, in order. Durations are measured; nothing is invented.")
        render_trace(result.get("trace"))
    with tabs[1]:
        _evidence_tab(result)
    with tabs[2]:
        _context_tab(result)
    with tabs[3]:
        _actions_tab(result)
    with tabs[4]:
        _similar_tab(result)
    with tabs[5]:
        _diagnosis_tab(result)
    with tabs[6]:
        _approval_tab(inc, result)
    with tabs[7]:
        _close_and_report_tab(inc, result)
    with tabs[8]:
        st.caption("Detailed event log, including retries and simulated events.")
        render_timeline(incident_repository.get_timeline(iid))


def render() -> None:
    st.title("🔎 New Investigation")
    mode_banner()
    if not [d for d in list_documents() if d["status"] == "indexed"]:
        st.caption("Tip: load the sample documents on the **Knowledge Base** page so the agent can search runbooks.")
    _start_section()
    st.divider()
    recent = incident_repository.list_incidents(include_seed=False, limit=30)
    if not recent:
        return
    ids = [r["id"] for r in recent]
    current = st.session_state.get("current_incident_id")
    idx = ids.index(current) if current in ids else 0
    chosen = st.selectbox("Investigation to view", ids, index=idx,
                          format_func=lambda i: next(f"{r['id']} - {r['title']} ({r['status']})" for r in recent if r["id"] == i))
    st.session_state["current_incident_id"] = chosen
    render_incident(chosen)
