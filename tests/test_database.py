import sqlite3

import pytest

from memory import incident_repository as repo
from memory.database import DatabaseError, connect, init_db


def test_schema_initialisation_creates_tables(db):
    with connect(db) as conn:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"incidents", "timeline_events", "audit_log", "documents", "doc_chunks", "reports",
            "investigation_results"} <= names


def test_seed_history_loaded_once(db):
    first = len(repo.list_incidents(db))
    init_db(db)  # second start-up must not duplicate seeds
    assert len(repo.list_incidents(db)) == first
    assert first >= 4


def test_incident_create_read_update(db):
    inc = repo.create_incident("Checkout failing", "payment-service", "SEV1", "desc", db_path=db)
    assert inc["id"].startswith("RC-") and inc["status"] == "open"
    upd = repo.update_incident(inc["id"], status="investigating", log_patterns=["db_timeout"], db_path=db)
    assert upd["status"] == "investigating" and upd["log_patterns"] == ["db_timeout"]
    assert repo.get_incident(inc["id"], db)["title"] == "Checkout failing"


def test_validation_errors(db):
    with pytest.raises(ValueError):
        repo.create_incident("t", "svc", "SEV9", db_path=db)
    with pytest.raises(ValueError):
        repo.create_incident(" ", "svc", "SEV1", db_path=db)
    inc = repo.create_incident("t", "svc", "SEV2", db_path=db)
    with pytest.raises(ValueError):
        repo.update_incident(inc["id"], db_path=db, id="hack")  # not an editable field
    with pytest.raises(ValueError):
        repo.update_incident(inc["id"], db_path=db, status="deleted")


def test_memory_persists_after_reopening_database(db):
    inc = repo.create_incident("Persist me", "order-service", "SEV3", db_path=db)
    repo.update_incident(inc["id"], root_cause="slow dependency", resolution="added timeout", db_path=db)
    # Simulate an application restart: brand-new connection, schema init runs again.
    init_db(db)
    raw = sqlite3.connect(str(db))
    row = raw.execute("SELECT root_cause FROM incidents WHERE id = ?", (inc["id"],)).fetchone()
    raw.close()
    assert row[0] == "slow dependency"


def test_timeline_result_report_and_export(db):
    inc = repo.create_incident("t", "svc", "SEV2", db_path=db)
    repo.add_timeline_event(inc["id"], "Intake", "created", simulated=True, db_path=db)
    tl = repo.get_timeline(inc["id"], db)
    assert tl[0]["simulated"] is True
    repo.save_result(inc["id"], {"a": 1}, db)
    repo.save_result(inc["id"], {"a": 2}, db)
    assert repo.get_result(inc["id"], db) == {"a": 2}
    repo.save_report(inc["id"], "# r", db)
    assert repo.list_reports(db)[0]["incident_id"] == inc["id"]
    assert inc["id"] in repo.export_history(db)


def test_parameterised_search_is_injection_safe(db):
    # A classic injection string must be treated as plain text.
    assert repo.list_incidents(db, search="x' OR '1'='1") == []


def test_unwritable_database_path_raises_friendly_error(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("not a directory")
    with pytest.raises(DatabaseError):
        init_db(blocker / "sub" / "db.sqlite")
