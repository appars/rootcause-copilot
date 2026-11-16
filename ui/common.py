"""Shared UI helpers: session state, mode handling, styling and small widgets.

Session state (temporary, per browser session) holds UI choices and the API key.
SQLite (durable) holds incident memory. Students should be able to point at
the difference: refresh the browser and the key is gone; restart the app and
incident history is still there.
"""
from __future__ import annotations

import os
from typing import Any

import streamlit as st

import config
from core.llm_client import GroqLLM, LLMError
from core.logging_setup import forget_secret, get_logger, register_secret
from core.trace import STATUS_ICONS

SEVERITY_COLORS = {"SEV1": "#b91c1c", "SEV2": "#c2410c", "SEV3": "#a16207", "SEV4": "#4b5563"}
STATUS_COLORS = {"open": "#2563eb", "investigating": "#2563eb", "awaiting_approval": "#c2410c",
                 "mitigated": "#0d9488", "closed": "#475569"}

CSS = """
<style>
.block-container {padding-top: 1.6rem; max-width: 1250px;}
.rc-badge {display:inline-block; padding:2px 10px; border-radius:12px; color:white; font-size:0.78rem;
           font-weight:600; margin-right:6px;}
.rc-banner-demo {background:#fff7ed; border:1px solid #fdba74; color:#9a3412; padding:8px 14px;
                 border-radius:8px; font-weight:600; margin-bottom:10px;}
.rc-banner-live {background:#ecfdf5; border:1px solid #6ee7b7; color:#065f46; padding:8px 14px;
                 border-radius:8px; font-weight:600; margin-bottom:10px;}
.rc-sim {color:#9a3412; font-weight:700;}
.rc-muted {color:#64748b; font-size:0.85rem;}
</style>
"""


def init_session() -> None:
    defaults: dict[str, Any] = {"mode": config.MODE_DEMO, "groq_api_key": None, "capability": None,
                                "current_incident_id": None, "failure_mode": "none",
                                "conn_status": None, "conn_message": ""}
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)


def server_key_available() -> bool:
    """True if the deployment provides GROQ_API_KEY (e.g. from a Kubernetes Secret). Value never shown."""
    return bool(os.getenv(config.GROQ_API_KEY_ENV, "").strip())


def active_api_key() -> str | None:
    """Session key first (student's own key), otherwise an optional server-side key."""
    return st.session_state.get("groq_api_key") or (os.getenv(config.GROQ_API_KEY_ENV) or None)


def masked_key() -> str:
    key = st.session_state.get("groq_api_key")
    if key:
        return f"\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022{key[-4:]}" if len(key) > 8 else "\u2022" * 8
    return "server-provided (hidden)" if server_key_available() else "not set"


def key_status_text() -> str:
    if st.session_state.get("groq_api_key"):
        return f"Session key {masked_key()}"
    if server_key_available():
        return "Server-provided key (hidden)"
    return "No key - Demo Mode available"


def connection_indicator() -> str:
    status = st.session_state.get("conn_status")
    if status == "ok":
        return "🟢 Connected - model available"
    if status in ("auth",):
        return "🔴 Key rejected by Groq"
    if status == "not_found":
        return "🔴 Model not accessible for this key"
    if status:
        return "🟠 Could not verify (network / timeout / rate limit / service)"
    if active_api_key():
        return "🟡 Key available - not tested yet"
    return "⚪ Not configured - Demo Mode available"


def get_llm() -> GroqLLM | None:
    key = active_api_key()
    if not key:
        return None
    return GroqLLM(key)


def is_live() -> bool:
    return st.session_state.get("mode") == config.MODE_LIVE


def connect_and_test(candidate: str | None) -> bool:
    """Make a REAL lightweight API request (model metadata). Only success switches to Live AI Mode."""
    key = (candidate or "").strip() or active_api_key()
    if not key:
        st.session_state.update(conn_status=None, conn_message="Paste your Groq API key first.")
        return False
    try:
        msg = GroqLLM(key).test_connection()
    except LLMError as e:
        st.session_state["conn_status"] = e.kind
        st.session_state["conn_message"] = e.user_message
        if candidate and e.transient:
            # Valid-looking key but the service could not be reached: keep it for a later retry.
            st.session_state["groq_api_key"] = key
            register_secret(key)
        get_logger("rootcause.ui").info("Groq connection test failed: %s", e.kind)
        return False
    if candidate:
        st.session_state["groq_api_key"] = key
        register_secret(key)
    st.session_state.update(conn_status="ok", conn_message=msg, mode=config.MODE_LIVE, live_activated=True)
    return True


def clear_api_key() -> None:
    forget_secret(st.session_state.get("groq_api_key"))
    st.session_state.update(groq_api_key=None, conn_status=None, conn_message="", capability=None)
    if not active_api_key():
        st.session_state["mode"] = config.MODE_DEMO


def sidebar_ai_configuration() -> None:
    """Sidebar block: key input (masked), Connect/Test, Clear, status, fixed model name."""
    sb = st.sidebar
    sb.markdown("### AI Configuration")
    sb.caption(f"Provider: **{config.LLM_PROVIDER}** · Model: `{config.LLM_MODEL}` (fixed)")
    with sb.form("ai_key_form", clear_on_submit=True):
        key = st.text_input("Groq API key", type="password", placeholder="paste your own key",
                            autocomplete="off", help="Kept only in this browser session on the server. "
                            "Never saved to disk, logs or reports.")
        connect = st.form_submit_button("🔌 Connect / Test connection", type="primary")
    if connect:
        with sb:
            with st.spinner("Contacting Groq..."):
                connect_and_test(key)
    sb.markdown(f"**Status:** {connection_indicator()}")
    sb.caption(f"Key: {masked_key()}")
    if st.session_state.get("conn_message") and st.session_state.get("conn_status") not in (None, "ok"):
        sb.error(st.session_state["conn_message"])
        sb.caption("You can keep working in **Demo Mode** (selected below).")
    elif st.session_state.get("conn_status") is None and st.session_state.get("conn_message"):
        sb.warning(st.session_state["conn_message"])
    if st.session_state.pop("live_activated", False):
        sb.success("Connection verified - Live AI Mode selected.")
    if st.session_state.get("groq_api_key") and sb.button("🗑️ Clear API key"):
        clear_api_key()
        sb.info("Key removed from this session.")


def mode_banner() -> None:
    if is_live():
        st.markdown(f"<div class='rc-banner-live'>LIVE AI MODE - investigations call {config.LLM_PROVIDER} "
                    f"(<code>{config.LLM_MODEL}</code>). The environment is still SIMULATED: no production "
                    "system is connected.</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='rc-banner-demo'>DEMO MODE - SIMULATED DEMO RESULTS: AI conclusions are "
                    "predefined and no live AI reasoning is performed. Log and YAML analysis still run for real. "
                    "No production system is connected.</div>", unsafe_allow_html=True)


def badge(text: str, color: str) -> str:
    return f"<span class='rc-badge' style='background:{color}'>{text}</span>"


def severity_badge(sev: str) -> str:
    return badge(sev, SEVERITY_COLORS.get(sev, "#475569"))


def status_badge(status: str) -> str:
    return badge(status.replace("_", " "), STATUS_COLORS.get(status, "#475569"))


def _on_mode_change() -> None:
    """Widget callback: refuse Live AI Mode without a key - visibly, never silently."""
    if st.session_state["mode_radio"] == config.MODE_LIVE and not active_api_key():
        st.session_state["mode_radio"] = config.MODE_DEMO
        st.session_state["mode_warning"] = True
    st.session_state["mode"] = st.session_state["mode_radio"]


def sidebar_mode_selector() -> None:
    st.sidebar.markdown("### Mode")
    # Keep the widget in step with the real mode (e.g. after Connect or Clear key).
    if st.session_state.get("mode_radio") != st.session_state["mode"]:
        st.session_state["mode_radio"] = st.session_state["mode"]
    st.sidebar.radio("Investigation mode", [config.MODE_LIVE, config.MODE_DEMO], key="mode_radio",
                     on_change=_on_mode_change, label_visibility="collapsed",
                     help="Live AI Mode calls Groq with your key. Demo Mode shows predefined, labelled results.")
    if st.session_state.pop("mode_warning", False):
        st.sidebar.warning("Live AI Mode needs a Groq API key - connect it above. Staying in Demo Mode.")


def offer_demo_mode(key: str) -> None:
    """Offer (never force) Demo Mode after a live failure."""
    if is_live() and st.button("➡️ Continue in Demo Mode", key=key):
        st.session_state["mode"] = config.MODE_DEMO
        st.rerun()


def friendly_llm_error(e: LLMError) -> None:
    st.error(f"**{e.kind.replace('_', ' ').title()}** - {e.user_message}")
    if e.kind in ("auth", "rate_limit", "connection", "timeout", "provider", "not_found"):
        st.info("Fix the key in the sidebar and retry, or continue in **Demo Mode** (predefined, clearly labelled "
                "results). RootCause Copilot never switches modes silently.")
        offer_demo_mode(f"demo_after_{e.kind}")


def render_timeline(events: list[dict[str, Any]]) -> None:
    if not events:
        st.caption("No timeline events yet.")
        return
    icons = {"ok": "✅", "warning": "⚠️", "retrying": "🔁", "recovered": "♻️", "degraded": "🟠",
             "failed": "❌", "waiting": "⏸️", "simulated": "🧪"}
    rows = []
    for e in events:
        rows.append({"Time (UTC)": e["ts"][11:19], "Stage": e["stage"],
                     "Event": ("[SIMULATED] " if e["simulated"] else "") + e["message"],
                     "Status": f"{icons.get(e['status'], '•')} {e['status']}"})
    st.dataframe(rows, hide_index=True, width="stretch",
                 column_config={"Event": st.column_config.TextColumn(width="large")})


def render_trace(trace: list[dict[str, Any]] | None) -> None:
    """The investigation execution trace: what ran, when, how long, and where each result came from."""
    if not trace:
        st.caption("No execution trace recorded for this investigation (created before v1.1).")
        return
    rows = []
    for s in trace:
        dur = s.get("duration_ms")
        rows.append({"Status": f"{STATUS_ICONS.get(s['status'], '•')} {s['status']}", "Step": s["step"],
                     "Started (UTC)": (s.get("started_at") or "-")[11:23] or "-",
                     "Duration": f"{dur:.1f} ms" if isinstance(dur, (int, float)) else "-",
                     "Origin": s.get("origin") or "-", "Result / finding": s.get("result") or "-",
                     "What this step does": s.get("explanation", "")})
    st.dataframe(rows, hide_index=True, width="stretch",
                 column_config={"Result / finding": st.column_config.TextColumn(width="large")})
    if any("SIMULATED DEMO RESULT" in (s.get("origin") or "") for s in trace):
        st.warning("Rows marked **SIMULATED DEMO RESULT** show predefined output - no AI reasoning ran. "
                   "All other 'executed' rows really ran in this session.")
