"""Data structures shared by the agent, tools and UI.

Results are plain JSON-serialisable dictionaries so they can be stored in
SQLite and rendered by Streamlit without conversion. The dataclasses below
document the shape and are used where structure matters most.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

CONFIDENCE_LEVELS = ("low", "medium", "high")
ROOT_CAUSE_CATEGORIES = (
    "database_connection_pool", "downstream_dependency", "memory_pressure", "configuration_error",
    "cpu_pressure", "code_defect", "network", "unknown",
)
# Every action that could change production. ALL of these require human approval.
PRODUCTION_CHANGING_ACTIONS = (
    "restart_service", "scale_deployment", "rollback_deployment", "update_configuration",
    "increase_resource_limits", "deploy_new_version", "failover_dependency",
)
READ_ONLY_ACTIONS = ("collect_more_evidence", "monitor_only", "notify_team")
ALL_ACTION_TYPES = PRODUCTION_CHANGING_ACTIONS + READ_ONLY_ACTIONS
# Educational risk level per action type (blast radius / reversibility). Unknown types are High.
ACTION_RISK = {
    "restart_service": "Medium", "scale_deployment": "Low", "rollback_deployment": "Medium",
    "update_configuration": "Medium", "increase_resource_limits": "Low", "deploy_new_version": "High",
    "failover_dependency": "High", "collect_more_evidence": "Low", "monitor_only": "Low", "notify_team": "Low",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class IncidentInput:
    """Everything the user (or a simulated alert) provides to start an investigation."""
    title: str
    service: str
    severity: str
    description: str = ""
    log_text: str = ""
    log_filename: str = ""
    yaml_text: str = ""
    yaml_filename: str = ""
    scenario_id: str | None = None          # set when a bundled sample scenario is used
    context_notes: str = ""                 # optional extra context from the user (untrusted text)
    trigger: dict[str, Any] = field(default_factory=lambda: {"type": "manual"})


@dataclass
class Hypothesis:
    summary: str
    root_cause_category: str = "unknown"
    supporting_evidence: list[str] = field(default_factory=list)
    confidence: str = "low"
    source: str = "rules"                    # llm | demo | rules

    def normalised(self) -> "Hypothesis":
        if self.confidence not in CONFIDENCE_LEVELS:
            self.confidence = "low"
        if self.root_cause_category not in ROOT_CAUSE_CATEGORIES:
            self.root_cause_category = "unknown"
        self.supporting_evidence = [str(e)[:300] for e in self.supporting_evidence][:8]
        self.summary = str(self.summary)[:800]
        return self

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Remediation:
    action: str
    action_type: str
    target: str
    evidence: list[str] = field(default_factory=list)
    expected_impact: str = ""
    risks: str = ""
    preconditions: str = ""
    rollback: str = ""

    @property
    def requires_approval(self) -> bool:
        # Unknown action types are treated as production-changing (fail safe).
        return self.action_type not in READ_ONLY_ACTIONS

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["requires_approval"] = self.requires_approval
        d["risk_level"] = ACTION_RISK.get(self.action_type, "High")
        return d
