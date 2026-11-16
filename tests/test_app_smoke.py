"""Smoke tests: run the real Streamlit app headlessly and click through it (Groq is mocked - no network)."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import config
from core.llm_client import GroqLLM, LLMError

APP = str(Path(__file__).resolve().parent.parent / "app.py")
FAKE_KEY = "test-placeholder-key-ABCD1234"


def _app():
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    assert not at.exception, at.exception
    return at


def _goto(at, page):
    at.sidebar.radio(key="page").set_value(page).run()
    assert not at.exception, at.exception


def _click(at, prefix):
    btn = next(b for b in at.button if b.label.startswith(prefix))
    btn.click().run()
    assert not at.exception, at.exception


def _connect(at, key):
    at.sidebar.text_input[0].input(key)
    next(b for b in at.sidebar.button if b.label.startswith("🔌 Connect")).click().run()
    assert not at.exception, at.exception


def test_app_starts_without_key_and_demo_is_available():
    at = _app()
    assert at.session_state["mode"] == config.MODE_DEMO
    assert at.session_state["groq_api_key"] is None
    assert any("DEMO MODE" in m.value and "SIMULATED DEMO RESULTS" in m.value for m in at.markdown)
    assert any("Not configured" in m.value for m in at.sidebar.markdown)
    assert any(config.LLM_MODEL in c.value for c in at.sidebar.caption)


@pytest.mark.parametrize("page", ["Dashboard", "New Investigation", "Incident History", "Knowledge Base",
                                  "Kubernetes Analyzer", "Investigation Reports", "Settings"])
def test_every_page_renders(page):
    _goto(_app(), page)


def test_sample_investigation_and_alert_from_ui():
    at = _app()
    _goto(at, "Knowledge Base")
    _click(at, "📥 Load bundled sample documents")
    _goto(at, "New Investigation")
    _click(at, "▶ Run sample investigation")
    assert any("completed" in s.value for s in at.success)
    assert any("Memory:" in s.value for s in at.success)          # retrieval feedback banner
    _click(at, "🚨 Simulate New Incident Alert")
    assert any("completed" in s.value for s in at.success) or any("Duplicate" in w.value for w in at.warning)


def test_connect_without_key_asks_for_one():
    at = _app()
    next(b for b in at.sidebar.button if b.label.startswith("🔌 Connect")).click().run()
    assert any("Paste your Groq API key first" in w.value for w in at.sidebar.warning)
    assert at.session_state["mode"] == config.MODE_DEMO


def test_invalid_key_is_rejected_not_stored(monkeypatch):
    def reject(self):
        raise LLMError("auth", "The Groq API key was rejected.")
    monkeypatch.setattr(GroqLLM, "test_connection", reject)
    at = _app()
    _connect(at, FAKE_KEY)
    assert at.session_state["groq_api_key"] is None
    assert at.session_state["mode"] == config.MODE_DEMO
    assert any("rejected" in e.value for e in at.sidebar.error)


def test_valid_key_connects_switches_to_live_and_is_masked(monkeypatch):
    monkeypatch.setattr(GroqLLM, "test_connection", lambda self: "Connected (mocked).")
    at = _app()
    _connect(at, FAKE_KEY)
    assert at.session_state["mode"] == config.MODE_LIVE
    assert at.session_state["conn_status"] == "ok"
    visible = " ".join(x.value for x in list(at.markdown) + list(at.caption) + list(at.sidebar.markdown)
                       + list(at.sidebar.caption) + list(at.success) + list(at.sidebar.success))
    assert FAKE_KEY not in visible and "1234" in visible          # only the last 4 characters are shown
    assert any("LIVE AI MODE" in m.value for m in at.markdown)
    next(b for b in at.sidebar.button if b.label.startswith("🗑️ Clear")).click().run()
    assert at.session_state["groq_api_key"] is None and at.session_state["mode"] == config.MODE_DEMO


def test_network_failure_keeps_key_for_retry_but_stays_in_demo(monkeypatch):
    def offline(self):
        raise LLMError("connection", "Could not reach the Groq API.", transient=True)
    monkeypatch.setattr(GroqLLM, "test_connection", offline)
    at = _app()
    _connect(at, FAKE_KEY)
    assert at.session_state["mode"] == config.MODE_DEMO
    assert at.session_state["conn_status"] == "connection"
    assert any("Demo Mode" in c.value for c in at.sidebar.caption)


def test_live_mode_refused_without_key_widget_and_state_agree():
    at = _app()
    at.sidebar.radio[1].set_value(config.MODE_LIVE).run()
    assert at.session_state["mode"] == config.MODE_DEMO
    assert at.sidebar.radio[1].value == config.MODE_DEMO
    assert any("needs a Groq API key" in w.value for w in at.sidebar.warning)


def test_settings_capability_check_without_key_shows_error():
    at = _app()
    _goto(at, "Settings")
    _click(at, "🧪 Run capability check")
    assert any("No key available" in e.value for e in at.error)
