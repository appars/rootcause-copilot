import config
from core.event_handler import scenario_input
from core.orchestrator import run_investigation
from memory import audit_repository, incident_repository
from tools.report_generator import generate_markdown_report, markdown_to_pdf


def test_markdown_and_pdf_report(db):
    r = run_investigation(scenario_input("INC-004"), config.MODE_DEMO, db_path=db)
    iid = r["incident_id"]
    md = generate_markdown_report(incident_repository.get_incident(iid, db), r,
                                  incident_repository.get_timeline(iid, db), audit_repository.list_audit_records(iid, db))
    for heading in ("1. Incident summary", "2. Incident metadata", "3. Symptoms", "4. Log analysis findings",
                    "5. Historical incident references", "6. Kubernetes findings", "7. Root-cause hypothesis",
                    "8. Supporting evidence", "9. Contradictory evidence", "10. Missing information",
                    "11. Recommended actions", "12. Human approval status", "13. Investigation timeline",
                    "14. Investigation mode", "15. Report generation"):
        assert f"## {heading}" in md, heading
    assert "SIMULATED DEMO RESULTS" in md and "Risk level" in md
    pdf = markdown_to_pdf(md + "\nUnicode test → — “quotes” नमस्ते")
    assert pdf[:5] == b"%PDF-" and len(pdf) > 1000


def test_report_handles_missing_result():
    inc = {"id": "X", "title": "t", "service": "s", "severity": "SEV3", "status": "open", "created_at": "now"}
    md = generate_markdown_report(inc, None, [], [])
    assert "No log file" in md and "## 15. Report generation" in md
