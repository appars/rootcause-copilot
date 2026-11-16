import pytest

import config
from core import approval
from core.event_handler import handle_alert, scenario_input, simulate_alert
from core.llm_client import LLMError
from core.orchestrator import run_investigation
from memory import audit_repository, incident_repository
from tools.document_search import ingest_sample_documents


def _run(db, sid="INC-001", failure="none"):
    return run_investigation(scenario_input(sid), config.MODE_DEMO, db_path=db, failure_mode=failure,
                             sleep=lambda s: None)


@pytest.mark.parametrize("sid", ["INC-001", "INC-002", "INC-003", "INC-004"])
def test_demo_mode_completes_each_scenario(db, sid):
    ingest_sample_documents(db)
    r = _run(db, sid)
    assert r["status"] == "completed" and r["mode"] == config.MODE_DEMO and r["llm_calls"] == 0
    assert r["hypothesis"]["source"] == "demo"
    assert 1 <= len(r["tool_calls"]) <= config.MAX_TOOL_CALLS
    assert len(r["reflection"]["rounds"]) <= config.MAX_REFLECTION_ROUNDS
    assert r["remediation"]["requires_approval"] is True
    assert incident_repository.get_incident(r["incident_id"], db)["status"] == "awaiting_approval"


def test_demo_mode_is_deterministic(tmp_path):
    from memory.database import init_db
    outs = []
    for i in range(2):
        path = tmp_path / f"d{i}.db"
        init_db(path)
        r = _run(path, "INC-003")
        outs.append(([c["tool"] for c in r["tool_calls"]], r["final"]["hypothesis"], r["final"]["confidence"]))
    assert outs[0] == outs[1]


def test_yaml_tool_only_used_when_yaml_present(db):
    assert "analyze_kubernetes_yaml" not in [c["tool"] for c in _run(db, "INC-001")["tool_calls"]]
    assert "analyze_kubernetes_yaml" in [c["tool"] for c in _run(db, "INC-004")["tool_calls"]]


def test_reflection_revises_overconfident_demo_hypothesis(db):
    r = _run(db, "INC-001")
    rounds = r["reflection"]["rounds"]
    assert rounds[0]["verdict"] == "revise" and len(rounds) == 2
    assert r["final"]["revised"] is True
    assert r["final"]["confidence"] != "high"


def test_similar_incident_from_memory(db):
    r = _run(db, "INC-001")
    assert r["evidence"]["similar_incidents"][0]["id"] == "HIST-2026-031"


def test_closed_incident_becomes_reusable_memory(db):
    first = _run(db, "INC-002")
    approval.close_incident(first["incident_id"], "Shipping quote dependency slow + retries",
                            "Reduced retries, added breaker", "Budget your retries", db_path=db)
    second = _run(db, "INC-002")
    ids = [s["id"] for s in second["evidence"]["similar_incidents"]]
    assert first["incident_id"] in ids


def test_event_driven_alert_and_deduplication(db):
    alert = simulate_alert("INC-001")
    assert alert["simulated"] is True
    inp, dup = handle_alert(alert, db)
    assert dup is None
    r = run_investigation(inp, config.MODE_DEMO, db_path=db, sleep=lambda s: None)
    tl = incident_repository.get_timeline(r["incident_id"], db)
    assert tl[0]["stage"] == "Event" and tl[0]["simulated"] is True
    inp2, dup2 = handle_alert(simulate_alert("INC-001"), db)
    assert inp2 is None and dup2 == r["incident_id"]


def test_transient_tool_failure_recovers(db):
    ingest_sample_documents(db)
    r = _run(db, "INC-001", failure="transient")
    kb = [c for c in r["tool_calls"] if c["tool"] == "search_knowledge_base"][0]
    assert kb["status"] == "recovered" and kb["attempts"] == 2
    assert any(e["status"] == "retrying" for e in incident_repository.get_timeline(r["incident_id"], db))


def test_persistent_tool_failure_degrades_honestly(db):
    ingest_sample_documents(db)
    r = _run(db, "INC-001", failure="persistent")
    kb = [c for c in r["tool_calls"] if c["tool"] == "search_knowledge_base"][0]
    assert kb["status"] == "failed"
    assert r["evidence"]["kb_results"] == []              # nothing invented
    assert any("search_knowledge_base" in l for l in r["final"]["limitations"])
    assert r["status"] == "completed"


def test_report_generated_and_labelled(db):
    r = _run(db)
    reports = incident_repository.list_reports(db)
    md = incident_repository.get_report(reports[0]["id"], db)["markdown"]
    assert r["incident_id"] in md and "Demo Mode" in md and "simulated" in md.lower()


def test_approval_flow_records_audit(db):
    r = _run(db)
    iid, rem = r["incident_id"], r["remediation"]
    with pytest.raises(ValueError):
        approval.record_decision(iid, rem, "reject", "asha", "", db_path=db)
    approval.record_decision(iid, rem, "more_info", "asha", "Need DB metrics", db_path=db)
    assert incident_repository.get_incident(iid, db)["status"] == "awaiting_approval"
    rec = approval.record_decision(iid, rem, "approve", "asha", "Evidence is clear", db_path=db)
    assert rec["new_status"] == "mitigated" and rec["execution"].startswith("SIMULATED ONLY")
    decisions = [a["decision"] for a in audit_repository.list_audit_records(iid, db)]
    assert decisions == ["requested", "more_info_requested", "approved"]


def test_read_only_action_needs_no_approval(db):
    inc = incident_repository.create_incident("t", "svc", "SEV3", db_path=db)
    rem = {"action": "Collect logs", "action_type": "collect_more_evidence", "target": "svc", "requires_approval": False}
    assert approval.request_approval(inc["id"], rem, db_path=db) == "investigating"
    assert audit_repository.list_audit_records(inc["id"], db)[0]["decision"] == "not_required"


def test_close_requires_root_cause_and_resolution(db):
    r = _run(db)
    with pytest.raises(ValueError):
        approval.close_incident(r["incident_id"], "", "", "", db_path=db)


def test_live_mode_without_key_is_refused(db):
    with pytest.raises(LLMError):
        run_investigation(scenario_input("INC-001"), config.MODE_LIVE, None, db_path=db)


def test_manual_incident_without_logs_reports_insufficient_evidence(db):
    from core.schemas import IncidentInput
    r = run_investigation(IncidentInput(title="Users report slowness", service="search-service", severity="SEV3",
                                        description="Vague report"), config.MODE_DEMO, db_path=db)
    assert r["final"]["confidence"] == "low"
    assert r["remediation"]["action_type"] == "collect_more_evidence"
    assert r["remediation"]["requires_approval"] is False
