"""Investigation orchestrator - the observable workflow that ties the seven concepts together.

    event / request -> incident intake -> agent selects tools (bounded loop)
    -> context selection -> root-cause hypothesis -> evidence verification (max 2 rounds)
    -> remediation proposal -> human approval gate -> report -> SQLite memory

Two records are kept for students:
* the execution TRACE (core/trace.py): one row per workflow step with status,
  real timestamp, measured duration and the ORIGIN of its result;
* the TIMELINE (SQLite): a detailed event log incl. retries and simulated events.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

import config
from core import approval
from core import trace as tr
from core.agent import LLMAgent, demo_diagnosis, rule_based_next_step, rules_diagnosis
from core.context_manager import build_context
from core.llm_client import GroqLLM, LLMError
from core.logging_setup import get_logger
from core.reflection import apply_review_adjustments, assess_evidence, deterministic_review, merge_reviews
from core.schemas import IncidentInput, utc_now
from core.tool_executor import InvestigationState, ToolExecutor, ToolResult
from core.tool_registry import ToolValidationError, llm_tool_definitions, parse_arguments, validate_tool_call
from memory import audit_repository, document_repository, incident_repository
from tools.log_analyzer import PATTERN_LABELS
from tools.report_generator import generate_markdown_report

log = get_logger("rootcause.orchestrator")
INTERNAL_ERROR_MESSAGE = ("An unexpected internal error stopped this investigation. Technical details were written "
                          "to the application log (no API keys are logged). Your inputs are preserved - you can retry.")


def _trim(data: Any, limit: int = config.TOOL_RESULT_MAX_CHARS) -> str:
    text = json.dumps(data, default=str)
    return text if len(text) <= limit else text[:limit] + '..."[truncated]"'


def run_investigation(inp: IncidentInput, mode: str, llm: GroqLLM | None = None, *,
                      db_path: str | Path | None = None, failure_mode: str = "none",
                      sleep: Callable[[float], None] = time.sleep,
                      on_trace: Callable[[list[dict[str, Any]]], None] | None = None) -> dict[str, Any]:
    if mode not in (config.MODE_DEMO, config.MODE_LIVE):
        raise ValueError(f"Unknown mode {mode!r}")
    if mode == config.MODE_LIVE and llm is None:
        raise LLMError("auth", "Live AI Mode needs a Groq API key. Connect it in the sidebar (AI Configuration), "
                               "or use Demo Mode.")
    if not inp.title.strip() or not inp.service.strip():
        raise ValueError("Incident title and service are required.")

    trace = tr.Trace(on_trace)
    trace.start("Incident Received")
    trigger = inp.trigger or {"type": "manual"}
    source = {"simulated_alert": "alert", "sample_scenario": "sample"}.get(trigger.get("type"), "manual")
    incident = incident_repository.create_incident(inp.title, inp.service, inp.severity, inp.description,
                                                   source=source, mode=mode, db_path=db_path)
    iid = incident["id"]

    def tl(stage: str, msg: str, status: str = "ok", simulated: bool = False) -> None:
        incident_repository.add_timeline_event(iid, stage, msg, status, simulated, db_path=db_path)

    result: dict[str, Any] = {"incident_id": iid, "mode": mode, "started_at": utc_now(), "trigger": trigger,
                              "scenario_id": inp.scenario_id, "status": "running", "tool_calls": [],
                              "errors": [], "failure_mode": failure_mode,
                              "context_notes": getattr(inp, "context_notes", "")}
    # ------------------------------------------------------------ 1. intake
    if trigger.get("type") == "simulated_alert":
        alert = trigger["alert"]
        tl("Event", f"Alert received: {alert['labels']['alertname']} ({alert['labels']['severity']}) - "
           f"{alert['annotations']['summary']}", simulated=True)
    tl("Intake", f"Incident {iid} created ({inp.severity}, {inp.service}) in {mode}.")
    if failure_mode != "none":
        tl("Instructor control", f"Failure simulation enabled: {failure_mode}.", "warning", simulated=True)
    incident_repository.update_incident(iid, status="investigating", db_path=db_path)

    evidence_bits = []
    if inp.log_text.strip():
        evidence_bits.append(f"log '{inp.log_filename or 'pasted text'}' ({len(inp.log_text.splitlines())} lines)")
    if inp.yaml_text.strip():
        evidence_bits.append(f"Kubernetes YAML '{inp.yaml_filename or 'pasted text'}'")
    tl("Evidence", "Evidence collected: " + (", ".join(evidence_bits) or "no files - metadata only") + ".")
    trace.finish("Incident Received", f"{iid} created ({inp.severity}, {inp.service}); trigger: "
                 f"{trigger.get('type', 'manual')}" + (" (SIMULATED alert)" if source == "alert" else "")
                 + "; evidence: " + (", ".join(evidence_bits) or "metadata only"))

    kb_docs = len([d for d in document_repository.list_documents(db_path) if d["status"] == "indexed"])
    state = InvestigationState(iid, inp.title, inp.service, inp.description, inp.log_text, inp.yaml_text,
                               kb_documents=kb_docs, context_notes=getattr(inp, "context_notes", ""))
    executor = ToolExecutor(state, db_path=db_path, failure_mode=failure_mode, sleep=sleep,
                            on_event=lambda stg, m, st, sim: tl(stg, m, st, sim))

    def record_call(name: str, args: dict[str, Any], reason: str, selected_by: str, res: ToolResult | None,
                    error: str = "") -> None:
        entry = {"tool": name, "arguments": args, "reason": reason, "selected_by": selected_by,
                 "status": res.status if res else "rejected", "summary": res.summary if res else error,
                 "attempts": res.attempts if res else 0}
        result["tool_calls"].append(entry)
        step = tr.TOOL_STEPS.get(name)
        if step and res is not None:
            trace.finish(step, f"{res.summary}" + (f" (selected by {selected_by}: {reason})" if reason else
                                                   f" (selected by {selected_by})"),
                         tr.ORIGIN_CODE, tr.COMPLETED if res.status in ("ok", "recovered") else tr.FAILED)
        tl("Tool", f"{name} [{selected_by}] - {entry['summary']}" + (f" Why: {reason}" if reason else ""),
           "ok" if entry["status"] in ("ok", "recovered") else "warning")

    def run_rule_step(selected_by: str) -> tuple[str, dict[str, Any], ToolResult] | None:
        step = rule_based_next_step(state)
        if step is None:
            return None
        name, args, reason = step
        clean, _ = validate_tool_call(name, args, llm_call=False)
        trace.start(tr.TOOL_STEPS[name])
        res = executor.run(name, clean)
        record_call(name, clean, reason, selected_by, res)
        return name, clean, res

    agent = LLMAgent(llm) if (mode == config.MODE_LIVE and llm) else None
    if llm is not None:
        llm.set_retry_callback(lambda m: tl("Error recovery", f"LLM call failed ({m}).", "retrying"))

    try:
        # -------------------------------------------- 2. dynamic tool selection
        if agent is None:
            while len(result["tool_calls"]) < config.MAX_TOOL_CALLS:
                if run_rule_step("rules (Demo Mode)") is None:
                    break
        else:
            messages = LLMAgent.initial_messages(state, kb_docs)
            tools = llm_tool_definitions()
            for _turn in range(config.MAX_AGENT_TURNS):
                if len(result["tool_calls"]) >= config.MAX_TOOL_CALLS:
                    tl("Agent", f"Tool-call limit reached ({config.MAX_TOOL_CALLS}); evidence collection stopped.", "warning")
                    break
                try:
                    reply = llm.chat_tools(messages, tools)  # type: ignore[union-attr]
                except LLMError as e:
                    if e.kind != "tool_use_failed":
                        raise
                    tl("Error recovery", "The model produced an invalid tool call; this step used deterministic "
                       "routing instead (still Live AI Mode).", "recovered")
                    step = run_rule_step("rules fallback (invalid model tool call)")
                    if step is None:
                        break
                    messages.append({"role": "user", "content": f"(System ran {step[0]} because your last tool call "
                                     f"was invalid. Result: {_trim(step[2].data, 1200)})"})
                    continue
                if not reply.tool_calls:
                    tl("Agent", "Model decided it has enough evidence (no further tool calls).")
                    break
                messages.append({"role": "assistant", "content": reply.content or None, "tool_calls": [
                    {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments_json}}
                    for c in reply.tool_calls]})
                for call in reply.tool_calls:
                    try:
                        clean, reason = validate_tool_call(call.name, parse_arguments(call.arguments_json))
                    except ToolValidationError as ve:
                        record_call(call.name, {}, "", "LLM (rejected)", None, f"Rejected before execution: {ve}")
                        messages.append({"role": "tool", "tool_call_id": call.id,
                                         "content": json.dumps({"error": f"Invalid tool call: {ve}"})})
                        continue
                    trace.start(tr.TOOL_STEPS[call.name])
                    res = executor.run(call.name, clean)
                    record_call(call.name, clean, reason, "LLM", res)
                    payload = res.data if res.status != "failed" else {"error": res.error, "note": "no result produced"}
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": _trim(payload)})
            if state.log_text.strip() and state.log_analysis is None:
                tl("Agent", "Safety step: logs analysed deterministically because the model did not request it.")
                trace.start("Log Analysis")
                res = executor.run("analyze_logs", {})
                record_call("analyze_logs", {}, "Orchestrator safety step", "orchestrator", res)

        _mark_skipped_tools(trace, state, agent is not None)

        # --------------------------------------------- 3. context selection
        trace.start("Context Extracted")
        context = build_context(state)
        result["context"] = context
        trace.finish("Context Extracted", f"{context['chars']} of {context['budget']} characters "
                     f"(~{context['approx_tokens']} tokens): " + ", ".join(s["section"] for s in context["included"])
                     + (f"; {len(context['excluded'])} item(s) excluded/truncated" if context["excluded"] else ""))
        tl("Context", f"Context selected: {context['chars']} of {context['budget']} characters "
           f"(~{context['approx_tokens']} tokens); sections: {', '.join(s['section'] for s in context['included'])}."
           + (" Some content was truncated or excluded." if context["truncated"] or context["excluded"] else ""))

        # ------------------------------------------------ 4. initial diagnosis
        trace.start("Root-Cause Hypothesis")
        if agent is None:
            diag = demo_diagnosis(inp.scenario_id) or rules_diagnosis(state)
            label = "precomputed demo output" if diag["source"] == "demo" else "rule-based heuristic (no LLM)"
        else:
            diag = agent.diagnose(context["text"])
            label = f"{config.LLM_MODEL} via {config.LLM_PROVIDER}"
        result["hypothesis"] = diag
        hyp_origin = {"demo": tr.ORIGIN_DEMO, "rules": tr.ORIGIN_RULES}.get(diag["source"], tr.ORIGIN_LLM)
        trace.finish("Root-Cause Hypothesis", f"Initial: {diag['hypothesis'][:300]}", hyp_origin)
        tl("Diagnosis", f"Initial hypothesis ({label}): {diag['hypothesis'][:220]} [confidence: {diag['confidence']}]")

        # ------------------------------------------------- 5. self-reflection
        trace.start("Evidence Verification")
        rounds = []
        current = diag
        review: dict[str, Any] = {}
        for r in range(1, config.MAX_REFLECTION_ROUNDS + 1):
            rule_review = deterministic_review(state, current)
            llm_review = None
            if agent is not None:
                try:
                    llm_review = agent.review(context["text"], current)
                except LLMError as e:
                    tl("Error recovery", f"LLM reviewer unavailable ({e.kind}); deterministic checks only.", "degraded")
            review = merge_reviews(rule_review, llm_review)
            round_assessment = assess_evidence(state, current, review)
            rounds.append({"round": r, "verdict": review["verdict"], "issues": review["issues"],
                           "checks": review["checks"], "reviewers": review["reviewers"],
                           "hypothesis_reviewed": current["hypothesis"],
                           "evidence_label": round_assessment["label_text"]})
            tl("Reflection", f"Round {r}: verdict '{review['verdict']}'" +
               (f" - {len(review['issues'])} issue(s): {review['issues'][0][:160]}" if review["issues"] else
                " - no issues found."), "ok" if review["verdict"] == "supported" else "warning")
            if review["verdict"] != "revise" or r == config.MAX_REFLECTION_ROUNDS:
                break
            if agent is None:
                revised = demo_diagnosis(inp.scenario_id, revised=True)
                current = revised if revised else apply_review_adjustments(current, review)
            else:
                current = agent.revise(context["text"], current, review["issues"])
            tl("Reflection", f"Hypothesis revised after review: {current['hypothesis'][:200]}")
        if review.get("verdict") == "revise":
            tl("Reflection", f"Reviewer still has concerns after {config.MAX_REFLECTION_ROUNDS} rounds; "
               "they are reported as limitations.", "warning")
        final = apply_review_adjustments(current, review)
        assessment = assess_evidence(state, current, review)
        trace.finish("Evidence Verification", f"{len(rounds)} round(s); final verdict '{review.get('verdict')}'; "
                     f"{assessment['label_text']}"
                     + (f". Hypothesis revised ({'predefined demo revision' if hyp_origin == tr.ORIGIN_DEMO else 'revision'})"
                        f": {final['hypothesis'][:200]}" if current is not diag else ""),
                     tr.ORIGIN_CODE if agent is None else "executed (deterministic checks + Groq LLM reviewer)")
        result["reflection"] = {"rounds": rounds, "final_verdict": review.get("verdict"),
                                "note": "Reflection reduces mistakes but does not guarantee correctness."}
        result["final"] = {"hypothesis": final["hypothesis"], "category": final["root_cause_category"],
                           "confidence": final["confidence"], "supporting_evidence": final["supporting_evidence"],
                           "alternatives": final["alternatives"], "limitations": final["limitations"],
                           "revised": current is not diag, "evidence_assessment": assessment}

        # ------------------------------------------ 6. remediation + approval
        remediation = dict(final["remediation"])
        remediation["reason"] = final["hypothesis"][:400]
        result["remediation"] = remediation
        new_status = approval.request_approval(iid, remediation, db_path=db_path)
        if remediation.get("requires_approval"):
            trace.await_human("Human Approval", f"Waiting for a human decision on: {remediation['action']} "
                              f"(risk: {remediation['risk_level']}). Nothing has been executed.")
        else:
            trace.skip("Human Approval", "Recommended action is read-only; no approval required.")
        result["next_steps"] = (
            ["Review the evidence and the proposed action", "Approve, reject or request more information"]
            if remediation.get("requires_approval") else ["Collect the missing evidence listed under limitations"])

        # --------------------------------------------- 7. memory write-back
        patterns = state.top_pattern_ids(6)
        symptoms = (f"{inp.title}. {inp.description[:300]} Observed: "
                    + ", ".join(PATTERN_LABELS[p] for p in patterns)).strip()
        incident_repository.update_incident(
            iid, symptoms=symptoms, log_patterns=patterns, hypothesis=final["hypothesis"],
            confidence=final["confidence"], status=new_status, supporting_evidence=assessment["supporting"],
            recommended_actions=remediation["action"], evidence_assessment=assessment["label_text"], db_path=db_path)
        result["status"] = "completed"
    except LLMError as e:
        trace.fail_running(f"Live AI unavailable ({e.kind})")
        result["status"] = "stopped"
        result["errors"].append({"kind": e.kind, "message": e.user_message})
        tl("Error recovery", f"Live AI unavailable ({e.kind}): {e.user_message} The investigation stopped; the "
           "evidence collected so far is preserved. Retry later or explicitly switch to Demo Mode - "
           "there is no silent fallback.", "failed")
        incident_repository.update_incident(iid, status="investigating", db_path=db_path)
        result.setdefault("context", build_context(state))
    except Exception as e:  # noqa: BLE001 - one broken investigation must not break the app
        log.exception("Investigation %s failed unexpectedly", iid)
        trace.fail_running(f"internal error ({type(e).__name__})")
        result["status"] = "failed"
        result["errors"].append({"kind": "internal", "message": INTERNAL_ERROR_MESSAGE})
        tl("Error", INTERNAL_ERROR_MESSAGE, "failed")
        incident_repository.update_incident(iid, status="investigating", db_path=db_path)

    # ------------------------------------------------------------- 8. report
    result["evidence"] = {"log_analysis": state.log_analysis, "yaml_analysis": state.yaml_analysis,
                          "yaml_error": state.yaml_error, "pattern_searches": state.pattern_searches,
                          "similar_incidents": state.similar_incidents, "kb_results": state.kb_results,
                          "unavailable_tools": state.unavailable}
    result["finished_at"] = utc_now()
    result["llm_calls"] = llm.calls_made if (llm is not None and mode == config.MODE_LIVE) else 0
    trace.start("Investigation Report Generated")
    result["trace"] = trace.to_list()
    incident_repository.save_result(iid, result, db_path=db_path)
    tl("Report", "Investigation report generated (generate_investigation_report).")
    trace.finish("Investigation Report Generated", "Markdown report saved; outcome written to SQLite memory.")
    result["trace"] = trace.to_list()
    incident_repository.save_result(iid, result, db_path=db_path)
    refresh_report(iid, db_path=db_path)
    return result


def _mark_skipped_tools(trace: tr.Trace, state: InvestigationState, live: bool) -> None:
    """Record WHY a tool step did not run (never pretend it ran)."""
    chooser = "The AI agent decided it was not needed" if live else "Rules decided it was not needed"
    reasons = {
        "Log Analysis": "No log file was provided." if not state.log_text.strip() else chooser,
        "Error Pattern Analysis": ("No log file was provided." if not state.log_text.strip() else
                                   "No known failure pattern was detected in the logs."
                                   if state.log_analysis and not state.log_analysis["patterns"] else chooser),
        "Historical Incident Search": chooser,
        "Knowledge Base Search": "No knowledge-base documents are indexed." if state.kb_documents == 0 else chooser,
        "Kubernetes Configuration Analysis": ("No Kubernetes YAML was attached." if not state.yaml_text.strip()
                                              else chooser),
    }
    for step, reason in reasons.items():
        trace.skip(step, reason)


def refresh_report(incident_id: str, db_path: str | Path | None = None) -> str:
    """generate_investigation_report - orchestrator-only tool. Saves a new report version."""
    incident = incident_repository.get_incident(incident_id, db_path)
    if incident is None:
        raise KeyError(incident_id)
    md = generate_markdown_report(incident, incident_repository.get_result(incident_id, db_path),
                                  incident_repository.get_timeline(incident_id, db_path),
                                  audit_repository.list_audit_records(incident_id, db_path))
    incident_repository.save_report(incident_id, md, db_path=db_path)
    return md
