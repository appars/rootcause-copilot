"""Approval / audit records (Concept 7 - Human-in-the-Loop).

Every human decision is written here with who, what, when and why, so the
approval history can be reviewed later. Rows are only ever inserted, never
updated - an append-only audit trail.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from memory.database import connect
from memory.incident_repository import now_iso

VALID_DECISIONS = ("requested", "approved", "rejected", "more_info_requested", "not_required")


def add_audit_record(
    incident_id: str,
    action: str,
    decision: str,
    reviewer: str = "",
    rationale: str = "",
    execution: str = "",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    if decision not in VALID_DECISIONS:
        raise ValueError(f"Decision must be one of {VALID_DECISIONS}")
    ts = now_iso()
    with connect(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO audit_log (incident_id, ts, action, decision, reviewer, rationale, execution)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (incident_id, ts, action, decision, reviewer.strip()[:80], rationale.strip()[:1000], execution),
        )
        rid = cur.lastrowid
    return {"id": rid, "incident_id": incident_id, "ts": ts, "action": action, "decision": decision,
            "reviewer": reviewer, "rationale": rationale, "execution": execution}


def list_audit_records(incident_id: str | None = None, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        if incident_id:
            rows = conn.execute("SELECT * FROM audit_log WHERE incident_id = ? ORDER BY id", (incident_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 200").fetchall()
    return [dict(r) for r in rows]
