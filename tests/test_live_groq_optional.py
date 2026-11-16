"""OPTIONAL live test against the real Groq API.

Skipped unless BOTH are set in the environment:
    GROQ_API_KEY   (your own key)
    RUN_LIVE_TESTS=1
It makes a few small requests and may count against your Groq limits.

PowerShell:
    $env:GROQ_API_KEY = Read-Host "Groq key"; $env:RUN_LIVE_TESTS = "1"; python -m pytest -m live
"""
import os

import pytest

import config

pytestmark = [pytest.mark.live,
              pytest.mark.skipif(not (os.getenv("GROQ_API_KEY") and os.getenv("RUN_LIVE_TESTS") == "1"),
                                 reason="live Groq test: set GROQ_API_KEY and RUN_LIVE_TESTS=1")]


def test_capability_check_against_real_groq():
    from core.llm_client import GroqLLM, run_capability_check
    report = run_capability_check(GroqLLM(os.environ["GROQ_API_KEY"]))
    assert report["connection"]["ok"], report
    assert report["tool_calling"]["ok"], report
    assert report["json_mode"]["ok"], report


def test_live_investigation_end_to_end(db):
    from core.event_handler import scenario_input
    from core.llm_client import GroqLLM
    from core.orchestrator import run_investigation
    r = run_investigation(scenario_input("INC-001"), config.MODE_LIVE, GroqLLM(os.environ["GROQ_API_KEY"]), db_path=db)
    assert r["status"] == "completed", r.get("errors")
    assert r["hypothesis"]["source"] == "llm"
    assert r["remediation"]["requires_approval"] in (True, False)
