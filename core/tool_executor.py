"""Executes allowlisted tools against the CURRENT investigation's evidence.

Concept 6 - Error Recovery for tools:
    transient failure -> bounded retry with backoff -> if still failing,
    continue WITHOUT that evidence and record the gap honestly.
    We never invent a tool result.

The instructor can switch on a clearly labelled simulated failure of the
knowledge-base tool to demonstrate this live.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import config
from tools import document_search, incident_retriever, kubernetes_analyzer, log_analyzer

FAILURE_MODES = {
    "none": "No simulated failure",
    "transient": "SIMULATED: knowledge base times out once, then recovers on retry",
    "persistent": "SIMULATED: knowledge base unavailable for the whole investigation",
}
TOOL_MAX_RETRIES = 2
TOOL_BACKOFF_SECONDS = 0.5


class ToolTransientError(RuntimeError):
    """A temporary failure that is worth retrying."""


class ToolFatalError(RuntimeError):
    """A failure that retrying will not fix."""


@dataclass
class InvestigationState:
    incident_id: str
    title: str
    service: str
    description: str = ""
    log_text: str = ""
    yaml_text: str = ""
    log_analysis: dict[str, Any] | None = None
    yaml_analysis: dict[str, Any] | None = None
    yaml_error: str | None = None
    pattern_searches: list[dict[str, Any]] = field(default_factory=list)
    similar_incidents: list[dict[str, Any]] = field(default_factory=list)
    kb_results: list[dict[str, Any]] = field(default_factory=list)
    tools_run: set[str] = field(default_factory=set)
    unavailable: dict[str, str] = field(default_factory=dict)   # tool -> reason it failed
    kb_documents: int = 0          # indexed knowledge-base documents (0 = searching is pointless)
    context_notes: str = ""        # optional extra context typed by the user

    def top_pattern_ids(self, n: int = 3) -> list[str]:
        if not self.log_analysis:
            return []
        return [p["id"] for p in self.log_analysis["patterns"][:n]]


@dataclass
class ToolResult:
    tool: str
    arguments: dict[str, Any]
    status: str                    # ok | failed | recovered
    summary: str
    data: Any = None
    attempts: int = 1
    error: str = ""


class ToolExecutor:
    def __init__(self, state: InvestigationState, *, db_path: str | Path | None = None,
                 failure_mode: str = "none", sleep: Callable[[float], None] = time.sleep,
                 on_event: Callable[[str, str, str, bool], None] | None = None):
        self.state = state
        self.db_path = db_path
        self.failure_mode = failure_mode if failure_mode in FAILURE_MODES else "none"
        self._kb_failures_left = {"none": 0, "transient": 1, "persistent": 10**6}[self.failure_mode]
        self._sleep = sleep
        self._on_event = on_event or (lambda stage, msg, status, simulated: None)

    # ------------------------------------------------------------ dispatch
    def run(self, name: str, args: dict[str, Any]) -> ToolResult:
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return ToolResult(name, args, "failed", f"No executor for '{name}'.", error="not implemented")
        attempts = 0
        while True:
            attempts += 1
            try:
                data, summary = handler(**args)
                self.state.tools_run.add(name)
                status = "recovered" if attempts > 1 else "ok"
                if attempts > 1:
                    self._on_event("Error recovery", f"{name} succeeded on attempt {attempts} after retry.", "recovered", False)
                return ToolResult(name, args, status, summary, data, attempts)
            except ToolTransientError as exc:
                if attempts > TOOL_MAX_RETRIES:
                    return self._give_up(name, args, attempts, f"{exc} (gave up after {attempts} attempts)")
                wait = TOOL_BACKOFF_SECONDS * (2 ** (attempts - 1))
                self._on_event("Error recovery", f"{name} failed: {exc}. Retrying in {wait:.1f}s "
                               f"(attempt {attempts + 1}/{TOOL_MAX_RETRIES + 1}).", "retrying",
                               "SIMULATED" in str(exc))
                self._sleep(wait)
            except ToolFatalError as exc:
                return self._give_up(name, args, attempts, str(exc))
            except Exception as exc:  # noqa: BLE001 - e.g. DatabaseError; never crash the investigation
                return self._give_up(name, args, attempts, f"{type(exc).__name__}: {exc}")

    def _give_up(self, name: str, args: dict[str, Any], attempts: int, error: str) -> ToolResult:
        self.state.unavailable[name] = error
        self.state.tools_run.add(name)
        self._on_event("Error recovery", f"{name} unavailable - continuing WITHOUT this evidence. Reason: {error}",
                       "degraded", "SIMULATED" in error)
        return ToolResult(name, args, "failed", f"Tool failed; no result was produced. {error}",
                          None, attempts, error)

    # --------------------------------------------------------------- tools
    def _tool_analyze_logs(self, focus_pattern: str | None = None) -> tuple[Any, str]:
        if not self.state.log_text.strip():
            raise ToolFatalError("No log file was provided for this incident.")
        analysis = log_analyzer.analyze_logs(self.state.log_text, focus_pattern)
        self.state.log_analysis = analysis
        return analysis, log_analyzer.summarize_for_display(analysis)

    def _tool_search_error_patterns(self, query: str) -> tuple[Any, str]:
        if not self.state.log_text.strip():
            raise ToolFatalError("No log file was provided for this incident.")
        res = log_analyzer.search_error_patterns(self.state.log_text, query)
        self.state.pattern_searches.append(res)
        return res, f"{res['match_count']} line(s) matched {res['label']}."

    def _tool_retrieve_similar_incidents(self, query: str, top_k: int = config.MAX_SIMILAR_INCIDENTS) -> tuple[Any, str]:
        res = incident_retriever.retrieve_similar_incidents(
            query, service=self.state.service, patterns=self.state.top_pattern_ids(5),
            top_k=top_k, exclude_id=self.state.incident_id, db_path=self.db_path)
        self.state.similar_incidents = res
        if not res:
            return res, "No sufficiently similar past incidents in memory."
        return res, "Found " + ", ".join(f"{r['id']} (score {r['score']})" for r in res) + "."

    def _tool_search_knowledge_base(self, query: str, top_k: int = config.MAX_KB_SNIPPETS) -> tuple[Any, str]:
        if self._kb_failures_left > 0:
            self._kb_failures_left -= 1
            raise ToolTransientError("SIMULATED knowledge-base timeout (instructor failure demo)")
        res = document_search.search_knowledge_base(query, top_k=top_k, db_path=self.db_path)
        self.state.kb_results = res
        if not res:
            return res, "No matching knowledge-base documents."
        return res, "Matched " + ", ".join(f"{r['filename']}" for r in res) + "."

    def _tool_analyze_kubernetes_yaml(self) -> tuple[Any, str]:
        if not self.state.yaml_text.strip():
            raise ToolFatalError("No Kubernetes YAML was attached to this incident.")
        try:
            res = kubernetes_analyzer.analyze_kubernetes_yaml(self.state.yaml_text)
        except kubernetes_analyzer.YamlParseError as exc:
            self.state.yaml_error = str(exc)
            raise ToolFatalError(str(exc)) from exc
        self.state.yaml_analysis = res
        return res, kubernetes_analyzer.summarize_findings(res)
