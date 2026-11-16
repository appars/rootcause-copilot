"""Live LLM Mode code path, exercised with a FAKE Groq client (no network, no API cost)."""
import config
from core.event_handler import scenario_input
from core.llm_client import GroqLLM, LLMError, classify_exception, run_capability_check
from core.orchestrator import run_investigation
from memory import incident_repository
from tests.fakes import (GOOD_DIAGNOSIS, SUPPORTED_REVIEW, AuthenticationError, BadRequestError, RateLimitError,
                         fake_client, json_response, text_response, tool_response)

FAKE_KEY = "gsk_TEST_KEY_SHOULD_NEVER_BE_STORED_1234567890"


def _llm(script, **kw):
    client, completions = fake_client(script)
    return GroqLLM(FAKE_KEY, client=client, sleep=lambda s: None, **kw), completions


def test_live_happy_path_with_tool_calling(db):
    llm, comp = _llm([
        tool_response("analyze_logs", {"reason": "start with facts"}, "c1"),
        tool_response("delete_database", {}, "c2"),                       # not allowlisted -> rejected
        tool_response("retrieve_similar_incidents", {"query": "connection pool checkout", "reason": "memory"}, "c3"),
        text_response("READY"),
        json_response(GOOD_DIAGNOSIS),
        json_response(SUPPORTED_REVIEW),
    ])
    r = run_investigation(scenario_input("INC-001"), config.MODE_LIVE, llm, db_path=db)
    assert r["status"] == "completed" and r["hypothesis"]["source"] == "llm"
    calls = [(c["tool"], c["status"], c["selected_by"]) for c in r["tool_calls"]]
    assert ("delete_database", "rejected", "LLM (rejected)") in calls
    assert ("retrieve_similar_incidents", "ok", "LLM") in calls
    assert r["llm_calls"] == 6
    # the fixed model and tool definitions were sent
    assert all(req["model"] == "openai/gpt-oss-20b" for req in comp.requests)
    assert "tools" in comp.requests[0] and comp.requests[4]["response_format"] == {"type": "json_object"}
    # the rejected call was reported back to the model as an error, never executed
    tool_msgs = [m for m in comp.requests[3]["messages"] if m["role"] == "tool"]
    assert any("Invalid tool call" in m["content"] for m in tool_msgs)


def test_tool_call_limit_is_enforced(db):
    # exactly MAX_TOOL_CALLS tool requests: the loop must stop before asking for more
    script = [tool_response("search_error_patterns", {"query": "pool"}, f"c{i}") for i in range(config.MAX_TOOL_CALLS)]
    script += [json_response(GOOD_DIAGNOSIS), json_response(SUPPORTED_REVIEW)]
    llm, _ = _llm(script)
    r = run_investigation(scenario_input("INC-001"), config.MODE_LIVE, llm, db_path=db)
    llm_calls = [c for c in r["tool_calls"] if c["selected_by"] == "LLM"]
    assert len(llm_calls) == config.MAX_TOOL_CALLS
    # safety step still guarantees the log facts exist
    assert r["evidence"]["log_analysis"] is not None


def test_reflection_rounds_are_bounded_in_live_mode(db):
    revise = dict(SUPPORTED_REVIEW, verdict="revise", issues=["still unsure"], confidence_justified=False,
                  suggested_confidence="low")
    llm, _ = _llm([text_response("READY"), json_response(GOOD_DIAGNOSIS), json_response(revise),
                   json_response(GOOD_DIAGNOSIS), json_response(revise)])
    r = run_investigation(scenario_input("INC-001"), config.MODE_LIVE, llm, db_path=db)
    assert len(r["reflection"]["rounds"]) == config.MAX_REFLECTION_ROUNDS == 2
    assert r["final"]["confidence"] == "low"


def test_invalid_key_stops_without_silent_demo_fallback(db):
    llm, comp = _llm([AuthenticationError("401")])
    r = run_investigation(scenario_input("INC-001"), config.MODE_LIVE, llm, db_path=db)
    assert r["status"] == "stopped" and r["errors"][0]["kind"] == "auth"
    assert r["mode"] == config.MODE_LIVE and "hypothesis" not in r     # no demo output substituted
    assert len(comp.requests) == 1                                     # auth errors are not retried
    assert incident_repository.get_incident(r["incident_id"], db)["status"] == "investigating"


def test_rate_limit_is_retried_a_bounded_number_of_times(db):
    llm, comp = _llm([RateLimitError("429")] * 5)
    r = run_investigation(scenario_input("INC-001"), config.MODE_LIVE, llm, db_path=db)
    assert len(comp.requests) == config.LLM_MAX_RETRIES + 1
    assert r["status"] == "stopped" and r["errors"][0]["kind"] == "rate_limit"
    tl = incident_repository.get_timeline(r["incident_id"], db)
    assert sum(1 for e in tl if e["status"] == "retrying") == config.LLM_MAX_RETRIES


def test_transient_error_then_success_recovers(db):
    llm, _ = _llm([RateLimitError("429"), text_response("READY"), json_response(GOOD_DIAGNOSIS),
                   json_response(SUPPORTED_REVIEW)])
    r = run_investigation(scenario_input("INC-001"), config.MODE_LIVE, llm, db_path=db)
    assert r["status"] == "completed"


def test_invalid_model_tool_call_uses_reported_rule_fallback(db):
    llm, _ = _llm([BadRequestError("tool_use_failed: invalid"), text_response("READY"),
                   json_response(GOOD_DIAGNOSIS), json_response(SUPPORTED_REVIEW)])
    r = run_investigation(scenario_input("INC-001"), config.MODE_LIVE, llm, db_path=db)
    assert r["tool_calls"][0]["selected_by"].startswith("rules fallback")
    assert r["status"] == "completed"


def test_invalid_json_twice_stops_honestly(db):
    llm, _ = _llm([text_response("READY"), text_response("not json"), text_response("still not json")])
    r = run_investigation(scenario_input("INC-001"), config.MODE_LIVE, llm, db_path=db)
    assert r["status"] == "stopped" and r["errors"][0]["kind"] == "invalid_output"


def test_api_key_never_persisted_or_displayed(db, tmp_path):
    llm, _ = _llm([text_response("READY"), json_response(GOOD_DIAGNOSIS), json_response(SUPPORTED_REVIEW)])
    assert FAKE_KEY not in repr(llm)
    r = run_investigation(scenario_input("INC-001"), config.MODE_LIVE, llm, db_path=db)
    assert FAKE_KEY not in str(r)
    assert FAKE_KEY.encode() not in db.read_bytes()


def test_error_classification():
    assert classify_exception(AuthenticationError()).transient is False
    assert classify_exception(RateLimitError()).transient is True
    assert classify_exception(BadRequestError("tool_use_failed")).kind == "tool_use_failed"


def test_capability_check_with_fake_client():
    llm, _ = _llm([tool_response("ping_tool", {"word": "hello"}), json_response({"status": "ok"})])
    report = run_capability_check(llm)
    assert report["connection"]["ok"] and report["tool_calling"]["ok"] and report["json_mode"]["ok"]


def test_empty_key_rejected():
    try:
        GroqLLM("  ")
    except LLMError as e:
        assert e.kind == "auth"
    else:
        raise AssertionError("expected LLMError")
