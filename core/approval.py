"""Human-in-the-Loop approval (Concept 7).

The agent may RECOMMEND. Only an authorised human may APPROVE. And even
after approval, this training application only SIMULATES the action:
no command is executed and no infrastructure is changed.

All production-changing action types require approval (restart, scale,
rollback, configuration change, resource-limit change, deployment,
failover) - and so does any action type the system does not recognise.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from core import trace as tr
from memory import audit_repository, incident_repository
from memory.incident_repository import add_timeline_event

DECISIONS = {"approve": "approved", "reject": "rejected", "more_info": "more_info_requested"}

_SIMULATED_COMMANDS = {
    "restart_service": "kubectl rollout restart deployment/{t}",
    "scale_deployment": "kubectl scale deployment/{t} --replicas=<n>",
    "rollback_deployment": "kubectl rollout undo deployment/{t}  (or git revert in the GitOps repo)",
    "update_configuration": "update ConfigMap for {t} in Git and let ArgoCD sync",
    "increase_resource_limits": "edit resources.limits for {t} in Git and let ArgoCD sync",
    "deploy_new_version": "update image tag for {t} in Git and let ArgoCD sync",
    "failover_dependency": "switch {t} to its secondary dependency endpoint",
}


def request_approval(incident_id: str, remediation: dict[str, Any], db_path: str | Path | None = None) -> str:
    """Record that approval is needed (or not needed for read-only actions). Returns new status."""
    action = f"{remediation['action_type']}: {remediation['action']}"
    if remediation.get("requires_approval", True):
        audit_repository.add_audit_record(incident_id, action, "requested",
                                          rationale="Production-changing action proposed by the agent.", db_path=db_path)
        add_timeline_event(incident_id, "Human approval", "Approval requested for a production-changing action. "
                           "Execution is PAUSED until a human decides.", "waiting", db_path=db_path)
        incident_repository.update_incident(incident_id, status="awaiting_approval", db_path=db_path)
        return "awaiting_approval"
    audit_repository.add_audit_record(incident_id, action, "not_required",
                                      rationale="Read-only action; no approval required.", db_path=db_path)
    add_timeline_event(incident_id, "Human approval", "Recommended action is read-only - no approval required.",
                       db_path=db_path)
    return "investigating"


def record_decision(incident_id: str, remediation: dict[str, Any], decision: str, reviewer: str = "",
                    rationale: str = "", db_path: str | Path | None = None) -> dict[str, Any]:
    """Approve / reject / request more information. Approval triggers a SIMULATED execution only."""
    if decision not in DECISIONS:
        raise ValueError(f"Unknown decision '{decision}'.")
    if decision in ("reject", "more_info") and not rationale.strip():
        raise ValueError("Please give a short rationale when rejecting or requesting more information.")
    action = f"{remediation['action_type']}: {remediation['action']}"
    execution = ""
    if decision == "approve":
        cmd = _SIMULATED_COMMANDS.get(remediation["action_type"], "<action>").format(t=remediation.get("target") or "<target>")
        execution = (f"SIMULATED ONLY - would run: {cmd}. No command was executed and no infrastructure was changed.")
        status, msg = "mitigated", f"Approved by {reviewer or 'unnamed reviewer'}. {execution}"
    elif decision == "reject":
        status, msg = "investigating", (f"Rejected by {reviewer or 'unnamed reviewer'}: {rationale}. "
                                        "Nothing was executed; choose an alternative or gather more evidence.")
    else:
        status, msg = "awaiting_approval", (f"More information requested by {reviewer or 'unnamed reviewer'}: "
                                            f"{rationale}. Execution remains paused.")
    record = audit_repository.add_audit_record(incident_id, action, DECISIONS[decision], reviewer, rationale,
                                               execution, db_path=db_path)
    add_timeline_event(incident_id, "Human approval", msg, "simulated" if decision == "approve" else "ok",
                       simulated=decision == "approve", db_path=db_path)
    incident_repository.update_incident(incident_id, status=status, db_path=db_path)
    _update_trace(incident_id, decision, reviewer, execution or rationale, db_path)
    return record | {"new_status": status}


def _update_trace(incident_id: str, decision: str, reviewer: str, note: str, db_path: str | Path | None) -> None:
    """Reflect the human decision in the saved execution trace (no duration is invented)."""
    result = incident_repository.get_result(incident_id, db_path)
    if not result or "trace" not in result:
        return
    label = {"approve": "Approved", "reject": "Rejected", "more_info": "More information requested"}[decision]
    status = tr.AWAITING if decision == "more_info" else tr.COMPLETED
    tr.update_stored_step(result["trace"], "Human Approval", status,
                          f"{label} by {reviewer or 'unnamed reviewer'}. {note}", tr.ORIGIN_HUMAN)
    incident_repository.save_result(incident_id, result, db_path)


def close_incident(incident_id: str, root_cause: str, resolution: str, lessons_learned: str,
                   db_path: str | Path | None = None) -> dict[str, Any]:
    """Engineer confirms the outcome. This is what turns an investigation into reusable MEMORY."""
    if not root_cause.strip() or not resolution.strip():
        raise ValueError("Root cause and resolution are required to close an incident.")
    inc = incident_repository.update_incident(incident_id, status="closed", root_cause=root_cause.strip(),
                                              resolution=resolution.strip(), lessons_learned=lessons_learned.strip(),
                                              db_path=db_path)
    add_timeline_event(incident_id, "Memory", "Incident closed; root cause, resolution and lessons learned saved to "
                       "persistent memory (SQLite) for future investigations.", db_path=db_path)
    return inc
