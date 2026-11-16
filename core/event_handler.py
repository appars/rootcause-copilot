"""Event-driven execution (Concept 4) - SIMULATED monitoring alerts.

In a real system, Prometheus evaluates alerting rules and Alertmanager
forwards firing alerts (e.g. via a webhook). Here we generate an
Alertmanager-style payload locally so no monitoring stack is required.

The event STARTS the workflow. What the agent does next is decided by the
agent itself (Concept 3).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import config
from core.schemas import IncidentInput, utc_now
from memory.incident_repository import list_incidents

SIMULATED_ALERTS: dict[str, dict[str, Any]] = {
    "INC-001": {"alertname": "PaymentServiceHighErrorRate", "service": "payment-service", "severity": "SEV1",
                "summary": "Checkout error rate above 5% and p95 latency above 2s for 5 minutes."},
    "INC-002": {"alertname": "OrderServiceLatencyHigh", "service": "order-service", "severity": "SEV2",
                "summary": "Order creation p95 latency above 4s; 504 responses rising."},
    "INC-003": {"alertname": "InventoryPodRestarting", "service": "inventory-service", "severity": "SEV2",
                "summary": "inventory-service containers restarted more than 3 times in 10 minutes."},
    "INC-004": {"alertname": "NotificationDeploymentUnavailable", "service": "notification-service", "severity": "SEV3",
                "summary": "notification-service has 0 available replicas after rollout."},
}


def load_scenarios() -> dict[str, dict[str, Any]]:
    data = json.loads(config.SCENARIOS_FILE.read_text(encoding="utf-8"))
    return {s["id"]: s for s in data}


def scenario_input(scenario_id: str, trigger: dict[str, Any] | None = None) -> IncidentInput:
    """Build an IncidentInput from a bundled synthetic scenario (logs + optional YAML)."""
    s = load_scenarios()[scenario_id]
    log_path = config.SAMPLE_LOGS_DIR / s["log_file"]
    yaml_text, yaml_name = "", ""
    if s.get("yaml_file"):
        yaml_path = config.SAMPLE_K8S_DIR / s["yaml_file"]
        yaml_text, yaml_name = yaml_path.read_text(encoding="utf-8"), yaml_path.name
    return IncidentInput(title=s["title"], service=s["service"], severity=s["severity"], description=s["description"],
                         log_text=log_path.read_text(encoding="utf-8"), log_filename=log_path.name,
                         yaml_text=yaml_text, yaml_filename=yaml_name, scenario_id=scenario_id,
                         trigger=trigger or {"type": "sample_scenario", "scenario": scenario_id})


def simulate_alert(scenario_id: str = "INC-001") -> dict[str, Any]:
    """Create an Alertmanager-style alert payload (SIMULATED)."""
    a = SIMULATED_ALERTS[scenario_id]
    labels = {"alertname": a["alertname"], "service": a["service"], "severity": a["severity"], "env": "training"}
    fingerprint = hashlib.sha256(json.dumps(labels, sort_keys=True).encode()).hexdigest()[:16]
    return {"status": "firing", "simulated": True, "source": "SIMULATED monitoring alert (no Prometheus connected)",
            "labels": labels, "annotations": {"summary": a["summary"]}, "startsAt": utc_now(),
            "fingerprint": fingerprint, "scenario_id": scenario_id}


def handle_alert(alert: dict[str, Any], db_path: str | Path | None = None) -> tuple[IncidentInput | None, str | None]:
    """Route an alert event into the investigation workflow.

    Returns (incident_input, duplicate_of). If an open incident already exists for the same
    alert fingerprint, the event is de-duplicated (no second investigation is started).
    """
    marker = f"[alert:{alert['fingerprint']}]"
    for inc in list_incidents(db_path, search=marker):
        if inc["status"] in ("open", "investigating", "awaiting_approval"):
            return None, inc["id"]
    trigger = {"type": "simulated_alert", "alert": alert}
    inp = scenario_input(alert["scenario_id"], trigger=trigger)
    inp.title = f"{alert['labels']['alertname']}: {inp.title}"
    inp.description = f"{alert['annotations']['summary']} {marker}\n{inp.description}"
    return inp, None
