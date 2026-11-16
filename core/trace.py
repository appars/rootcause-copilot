"""Investigation execution trace - what the agent ACTUALLY did, step by step.

Rules this module enforces:
* A step's timestamp and duration are recorded only when it really runs
  (time.perf_counter); nothing is invented.
* Every step states its ORIGIN: real code execution, a Groq LLM call,
  a rule-based heuristic, or a predefined SIMULATED DEMO RESULT.
* Steps that never ran stay "Pending"; steps deliberately not needed are
  "Skipped" with the reason.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable

PENDING, RUNNING, COMPLETED, FAILED, SKIPPED, AWAITING = (
    "Pending", "Running", "Completed", "Failed", "Skipped", "Awaiting Approval")
STATUS_ICONS = {PENDING: "⏳", RUNNING: "🔄", COMPLETED: "✅", FAILED: "❌", SKIPPED: "⏭️", AWAITING: "⏸️"}

ORIGIN_CODE = "executed (deterministic code)"
ORIGIN_LLM = "executed (Groq LLM call)"
ORIGIN_RULES = "executed (rule-based heuristic - no AI)"
ORIGIN_DEMO = "SIMULATED DEMO RESULT (predefined - no AI reasoning)"
ORIGIN_HUMAN = "human decision (simulated approval workflow)"

STEPS: dict[str, str] = {
    "Incident Received": "An alert or a user request creates the incident record.",
    "Log Analysis": "Deterministic parsing: counts, time range, exceptions, stack traces, patterns, sequence.",
    "Error Pattern Analysis": "Inspect the lines behind the most relevant failure pattern.",
    "Historical Incident Search": "Search persistent SQLite memory for similar past incidents.",
    "Knowledge Base Search": "Search runbooks/documents; only relevant excerpts are kept.",
    "Kubernetes Configuration Analysis": "Static checks on attached Kubernetes YAML (Secrets masked).",
    "Context Extracted": "Select, rank and trim the evidence that will be reasoned over.",
    "Root-Cause Hypothesis": "Form a probable root cause from the selected evidence.",
    "Evidence Verification": "Reviewer checks the hypothesis against the evidence (max 2 rounds).",
    "Human Approval": "Production-changing actions wait for a human decision.",
    "Investigation Report Generated": "Write the Markdown report and save the outcome to memory.",
}
TOOL_STEPS = {
    "analyze_logs": "Log Analysis",
    "search_error_patterns": "Error Pattern Analysis",
    "retrieve_similar_incidents": "Historical Incident Search",
    "search_knowledge_base": "Knowledge Base Search",
    "analyze_kubernetes_yaml": "Kubernetes Configuration Analysis",
    "generate_investigation_report": "Investigation Report Generated",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Trace:
    def __init__(self, on_update: Callable[[list[dict[str, Any]]], None] | None = None):
        self._steps: dict[str, dict[str, Any]] = {
            name: {"step": name, "status": PENDING, "started_at": None, "duration_ms": None,
                   "explanation": expl, "result": "", "origin": "", "runs": 0, "_order": None}
            for name, expl in STEPS.items()}
        self._t0: dict[str, float] = {}
        self._counter = 0
        self._on_update = on_update or (lambda steps: None)

    # -------------------------------------------------------------- updates
    def start(self, name: str, explanation: str | None = None) -> None:
        s = self._steps[name]
        self._counter += 1
        if s["_order"] is None:
            s["_order"] = self._counter
            s["started_at"] = _now()
        s["status"] = RUNNING
        s["runs"] += 1
        if explanation:
            s["explanation"] = explanation
        self._t0[name] = time.perf_counter()
        self._emit()

    def finish(self, name: str, result: str = "", origin: str = ORIGIN_CODE, status: str = COMPLETED) -> None:
        s = self._steps[name]
        if name in self._t0:
            elapsed = (time.perf_counter() - self._t0.pop(name)) * 1000
            s["duration_ms"] = round((s["duration_ms"] or 0) + elapsed, 1)
        s["status"] = status
        s["origin"] = origin
        s["result"] = (f"{s['result']} | {result}" if s["result"] and s["runs"] > 1 else result)[:600]
        self._emit()

    def await_human(self, name: str, result: str) -> None:
        """A step that waits for a person: timestamp yes, duration no (it is not measurable yet)."""
        s = self._steps[name]
        self._counter += 1
        s.update(status=AWAITING, result=result[:600], origin=ORIGIN_HUMAN, started_at=_now(),
                 _order=s["_order"] or self._counter, runs=s["runs"] + 1)
        self._emit()

    def fail(self, name: str, error: str, origin: str = ORIGIN_CODE) -> None:
        self.finish(name, f"Failed: {error}", origin, FAILED)

    def skip(self, name: str, reason: str) -> None:
        s = self._steps[name]
        if s["status"] == PENDING:
            self._counter += 1
            s.update(status=SKIPPED, result=reason, origin="not executed", _order=self._counter)
            self._emit()

    def fail_running(self, error: str) -> None:
        for name, s in self._steps.items():
            if s["status"] == RUNNING:
                self.fail(name, error, s["origin"] or ORIGIN_CODE)

    def status(self, name: str) -> str:
        return self._steps[name]["status"]

    # --------------------------------------------------------------- output
    def to_list(self) -> list[dict[str, Any]]:
        """Executed/skipped steps in real order, then steps that never ran (Pending)."""
        done = sorted((s for s in self._steps.values() if s["_order"] is not None), key=lambda s: s["_order"])
        pending = [s for s in self._steps.values() if s["_order"] is None]
        return [{k: v for k, v in s.items() if k != "_order"} for s in done + pending]

    def _emit(self) -> None:
        try:
            self._on_update(self.to_list())
        except Exception:  # noqa: BLE001 - a UI refresh problem must never break the investigation
            pass


def update_stored_step(trace_list: list[dict[str, Any]], name: str, status: str, result: str, origin: str) -> None:
    """Update a step in a saved trace (e.g. when the human decides later). No duration is invented."""
    for s in trace_list:
        if s["step"] == name:
            s.update(status=status, result=result[:600], origin=origin)
            if s["started_at"] is None:
                s["started_at"] = _now()
            return
