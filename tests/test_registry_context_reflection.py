import pytest

import config
from core.agent import normalise_diagnosis
from core.context_manager import build_context, find_injection_lines
from core.reflection import deterministic_review, merge_reviews
from core.tool_executor import InvestigationState, ToolExecutor
from core.tool_registry import ToolValidationError, llm_tool_definitions, parse_arguments, validate_tool_call


# ------------------------------------------------------------- tool registry
def test_unknown_tool_rejected():
    with pytest.raises(ToolValidationError, match="allowlist"):
        validate_tool_call("delete_database", {})


def test_report_tool_not_selectable_by_model():
    assert "generate_investigation_report" not in {d["function"]["name"] for d in llm_tool_definitions()}
    with pytest.raises(ToolValidationError):
        validate_tool_call("generate_investigation_report", {})
    validate_tool_call("generate_investigation_report", {}, llm_call=False)


@pytest.mark.parametrize("name,args,msg", [
    ("search_error_patterns", {}, "Missing"),
    ("search_error_patterns", {"query": "x" * 61}, "longer"),
    ("search_error_patterns", {"query": "a", "shell": "rm -rf /"}, "Unexpected"),
    ("retrieve_similar_incidents", {"query": "a", "top_k": 50}, "between"),
    ("retrieve_similar_incidents", {"query": "a", "top_k": "lots"}, "integer"),
    ("analyze_logs", {"focus_pattern": "not_a_pattern"}, "one of"),
])
def test_invalid_arguments_rejected(name, args, msg):
    with pytest.raises(ToolValidationError, match=msg):
        validate_tool_call(name, args)


def test_reason_is_separated_and_args_cleaned():
    clean, reason = validate_tool_call("retrieve_similar_incidents", {"query": "  pool  ", "top_k": "3", "reason": "why"})
    assert clean == {"query": "pool", "top_k": 3} and reason == "why"


def test_parse_arguments():
    assert parse_arguments('{"a": 1}') == {"a": 1}
    with pytest.raises(ToolValidationError):
        parse_arguments("[1,2]")
    with pytest.raises(ToolValidationError):
        parse_arguments("{bad json")


# ----------------------------------------------------------- context manager
def _state(name="inc001_payment_service.log", **kw):
    text = (config.SAMPLE_LOGS_DIR / name).read_text(encoding="utf-8")
    st = InvestigationState("RC-T", "Checkout failures", "payment-service", "desc", text, **kw)
    ToolExecutor(st).run("analyze_logs", {})
    return st


def test_context_respects_budget_and_reports_truncation():
    ctx = build_context(_state(), budget=800)
    assert ctx["chars"] <= 800
    assert ctx["truncated"] is True
    assert ctx["excluded"]


def test_context_collapses_duplicates_and_limits_lines():
    ctx = build_context(_state())
    assert ctx["chars"] <= config.MAX_CONTEXT_CHARS
    assert any("duplicate occurrences collapsed" in n for n in ctx["notes"])
    assert "<untrusted_evidence>" in ctx["text"]


def test_prompt_injection_is_flagged_not_obeyed():
    st = _state("inc002_order_service.log")
    assert find_injection_lines(st.log_text)
    ctx = build_context(st)
    assert any("prompt-injection" in n for n in ctx["notes"])


def test_unavailable_tool_listed_as_excluded():
    st = _state()
    st.unavailable["search_knowledge_base"] = "SIMULATED outage"
    assert any("search_knowledge_base" in e for e in build_context(st)["excluded"])


# ---------------------------------------------------------------- reflection
def _diag(**over):
    base = {"hypothesis": "The connection pool is exhausted.", "root_cause_category": "database_connection_pool",
            "supporting_evidence": ["L30: pool idle=0"], "confidence": "medium",
            "remediation": {"action": "restart", "action_type": "restart_service", "target": "payment-service"}}
    base.update(over)
    return normalise_diagnosis(base, "llm")


def test_supported_diagnosis_passes():
    assert deterministic_review(_state(), _diag())["verdict"] == "supported"


def test_unsupported_deployment_claim_is_caught_but_negation_is_not():
    st = _state()
    bad = deterministic_review(st, _diag(hypothesis="The pool is exhausted because of the new deployment."))
    assert bad["verdict"] == "revise" and any("deployment" in i for i in bad["issues"])
    ok = deterministic_review(st, _diag(hypothesis="The pool is exhausted. No deployment evidence was found."))
    assert ok["verdict"] == "supported"


def test_nonexistent_line_reference_caught():
    r = deterministic_review(_state(), _diag(supporting_evidence=["L9999: invented line"]))
    assert any("do not exist" in i for i in r["issues"])


def test_overconfidence_downgraded_and_wrong_category_flagged():
    r = deterministic_review(_state(), _diag(confidence="high", root_cause_category="memory_pressure",
                                             remediation={"action": "x", "action_type": "increase_resource_limits"}))
    assert r["verdict"] == "revise"
    assert r["suggested_confidence"] in ("low", "medium")
    assert any("more supporting evidence" in i for i in r["issues"])


def test_no_evidence_is_insufficient():
    st = InvestigationState("RC-T", "t", "svc")
    r = deterministic_review(st, _diag(root_cause_category="unknown", confidence="low",
                                       remediation={"action": "x", "action_type": "collect_more_evidence"}))
    assert r["verdict"] == "insufficient"


def test_merge_takes_the_stricter_verdict():
    rule = deterministic_review(_state(), _diag())
    llm = {"verdict": "revise", "issues": ["needs DB metrics"], "missing_evidence": [], "alternatives": [],
           "confidence_justified": False, "suggested_confidence": "low"}
    merged = merge_reviews(rule, llm)
    assert merged["verdict"] == "revise" and merged["suggested_confidence"] == "low"


def test_unknown_action_type_requires_approval():
    d = _diag(remediation={"action": "drop the database", "action_type": "drop_database"})
    assert d["remediation"]["action_type"] == "unclassified_action"
    assert d["remediation"]["requires_approval"] is True
