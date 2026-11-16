"""Incident records, timeline events and saved investigation results."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from memory.database import connect

EDITABLE_FIELDS = {
    "title", "service", "severity", "status", "description", "symptoms", "log_patterns",
    "hypothesis", "root_cause", "resolution", "lessons_learned", "confidence", "mode",
    "supporting_evidence", "recommended_actions", "evidence_assessment",
}
VALID_SEVERITIES = ("SEV1", "SEV2", "SEV3", "SEV4")
VALID_STATUSES = ("open", "investigating", "awaiting_approval", "mitigated", "closed")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _row_to_dict(row: Any) -> dict[str, Any]:
    d = dict(row)
    for key in ("log_patterns", "supporting_evidence"):
        try:
            d[key] = json.loads(d.get(key) or "[]")
        except (json.JSONDecodeError, TypeError):
            d[key] = []
    return d


def next_incident_id(db_path: str | Path | None = None) -> str:
    """Generate IDs like RC-0001 for investigations created in the app."""
    with connect(db_path) as conn:
        rows = conn.execute("SELECT id FROM incidents WHERE id LIKE 'RC-%'").fetchall()
    numbers = [int(r["id"].split("-")[1]) for r in rows if r["id"].split("-")[1].isdigit()]
    return f"RC-{(max(numbers) + 1) if numbers else 1:04d}"


def create_incident(
    title: str,
    service: str,
    severity: str,
    description: str = "",
    source: str = "manual",
    mode: str = "",
    incident_id: str | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    if not title.strip() or not service.strip():
        raise ValueError("Incident title and service are required.")
    if severity not in VALID_SEVERITIES:
        raise ValueError(f"Severity must be one of {VALID_SEVERITIES}.")
    incident_id = incident_id or next_incident_id(db_path)
    ts = now_iso()
    with connect(db_path) as conn:
        conn.execute(
            """INSERT INTO incidents (id, title, service, severity, status, source, description,
                                       mode, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'open', ?, ?, ?, ?, ?)""",
            (incident_id, title.strip(), service.strip(), severity, source, description.strip(), mode, ts, ts),
        )
    return get_incident(incident_id, db_path)  # type: ignore[return-value]


def get_incident(incident_id: str, db_path: str | Path | None = None) -> dict[str, Any] | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone()
    return _row_to_dict(row) if row else None


def update_incident(incident_id: str, db_path: str | Path | None = None, **fields: Any) -> dict[str, Any]:
    unknown = set(fields) - EDITABLE_FIELDS
    if unknown:
        raise ValueError(f"Cannot update fields: {sorted(unknown)}")
    if "status" in fields and fields["status"] not in VALID_STATUSES:
        raise ValueError(f"Invalid status {fields['status']!r}")
    for key in ("log_patterns", "supporting_evidence"):
        if key in fields and not isinstance(fields[key], str):
            fields[key] = json.dumps(fields[key])
    if not fields:
        return get_incident(incident_id, db_path) or {}
    # Column names come from the EDITABLE_FIELDS allowlist; values are parameterised.
    assignments = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [now_iso(), incident_id]
    with connect(db_path) as conn:
        cur = conn.execute(f"UPDATE incidents SET {assignments}, updated_at = ? WHERE id = ?", values)
        if cur.rowcount == 0:
            raise KeyError(f"Incident {incident_id} not found")
    return get_incident(incident_id, db_path) or {}


def list_incidents(
    db_path: str | Path | None = None,
    search: str = "",
    service: str = "",
    include_seed: bool = True,
    limit: int = 200,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM incidents WHERE 1=1"
    params: list[Any] = []
    if search:
        like = f"%{search.strip()}%"
        sql += (" AND (title LIKE ? OR symptoms LIKE ? OR root_cause LIKE ? OR resolution LIKE ?"
                " OR lessons_learned LIKE ? OR id LIKE ? OR log_patterns LIKE ?)")
        params += [like] * 7
    if service:
        sql += " AND service = ?"
        params.append(service)
    if not include_seed:
        sql += " AND source != 'seed'"
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(int(limit))
    with connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def incident_counts(db_path: str | Path | None = None) -> dict[str, int]:
    with connect(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM incidents WHERE source != 'seed'").fetchone()[0]
        history = conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
        open_ = conn.execute(
            "SELECT COUNT(*) FROM incidents WHERE source != 'seed' AND status IN ('open','investigating','awaiting_approval')"
        ).fetchone()[0]
        closed = conn.execute(
            "SELECT COUNT(*) FROM incidents WHERE source != 'seed' AND status IN ('mitigated','closed')"
        ).fetchone()[0]
    return {"investigations": total, "open": open_, "completed": closed, "memory_records": history}


# ---------------------------------------------------------------- timeline
def add_timeline_event(
    incident_id: str, stage: str, message: str, status: str = "ok", simulated: bool = False,
    ts: str | None = None, db_path: str | Path | None = None,
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO timeline_events (incident_id, ts, stage, message, status, simulated) VALUES (?, ?, ?, ?, ?, ?)",
            (incident_id, ts or now_iso(), stage, message, status, int(simulated)),
        )


def get_timeline(incident_id: str, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT ts, stage, message, status, simulated FROM timeline_events WHERE incident_id = ? ORDER BY id",
            (incident_id,),
        ).fetchall()
    return [dict(r) | {"simulated": bool(r["simulated"])} for r in rows]


# ------------------------------------------------------- investigation result
def save_result(incident_id: str, result: dict[str, Any], db_path: str | Path | None = None) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """INSERT INTO investigation_results (incident_id, result_json, updated_at) VALUES (?, ?, ?)
               ON CONFLICT(incident_id) DO UPDATE SET result_json = excluded.result_json,
                                                      updated_at = excluded.updated_at""",
            (incident_id, json.dumps(result, default=str), now_iso()),
        )


def get_result(incident_id: str, db_path: str | Path | None = None) -> dict[str, Any] | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT result_json FROM investigation_results WHERE incident_id = ?", (incident_id,)).fetchone()
    return json.loads(row["result_json"]) if row else None


# ------------------------------------------------------------------ reports
def save_report(incident_id: str, markdown: str, db_path: str | Path | None = None) -> None:
    with connect(db_path) as conn:
        conn.execute("INSERT INTO reports (incident_id, markdown, created_at) VALUES (?, ?, ?)",
                     (incident_id, markdown, now_iso()))


def list_reports(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        rows = conn.execute(
            """SELECT r.id, r.incident_id, r.created_at, i.title, i.service, i.severity
               FROM reports r LEFT JOIN incidents i ON i.id = r.incident_id ORDER BY r.id DESC"""
        ).fetchall()
    return [dict(r) for r in rows]


def get_report(report_id: int, db_path: str | Path | None = None) -> dict[str, Any] | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    return dict(row) if row else None


def export_history(db_path: str | Path | None = None) -> str:
    """Export all incidents as JSON (no secrets are ever stored, so this is safe to share)."""
    return json.dumps(list_incidents(db_path, limit=10_000), indent=2, default=str)


def distribution(db_path: str | Path | None = None, include_seed: bool = False) -> dict[str, dict[str, int]]:
    """Counts by severity and by service. Seed (fictional history) is excluded unless asked for."""
    where = "" if include_seed else "WHERE source != 'seed'"
    with connect(db_path) as conn:
        sev = conn.execute(f"SELECT severity, COUNT(*) n FROM incidents {where} GROUP BY severity ORDER BY severity").fetchall()
        svc = conn.execute(f"SELECT service, COUNT(*) n FROM incidents {where} GROUP BY service ORDER BY n DESC").fetchall()
    return {"severity": {r["severity"]: r["n"] for r in sev}, "service": {r["service"]: r["n"] for r in svc}}
