"""Settings / AI Configuration page.

The API key itself is entered in the sidebar (AI Configuration). The key:
* is typed into a password field and never displayed in full afterwards,
* is kept ONLY in this server-side Streamlit session (st.session_state),
* is never written to SQLite, logs, reports, files or Git,
* disappears when the browser session ends or "Clear API key" is clicked.
"""
from __future__ import annotations

import streamlit as st

import config
from core.llm_client import GroqLLM, run_capability_check
from ui.common import active_api_key, connection_indicator, masked_key, server_key_available


def render() -> None:
    st.title("⚙️ Settings / AI Configuration")
    st.subheader("LLM provider (fixed for this workshop)")
    c1, c2 = st.columns(2)
    c1.text_input("Provider", value=config.LLM_PROVIDER, disabled=True)
    c2.text_input("Model", value=config.LLM_MODEL, disabled=True)
    st.caption("Groq is the only live AI provider. There is no local model and no model download.")

    st.subheader("Your Groq API key")
    st.markdown("Enter and test your key in the **sidebar → AI Configuration**. *Connect / Test connection* makes a "
                "real, lightweight API request (it retrieves the fixed model's metadata - no tokens are generated) "
                "and only reports success when Groq accepts the key **and** the model is accessible.")
    st.markdown(f"**Status:** {connection_indicator()}  ·  **Key:** {masked_key()}")
    if server_key_available() and not st.session_state.get("groq_api_key"):
        st.info("This deployment provides a server-side key (for example from a Kubernetes Secret). Its value is "
                "never shown. Everyone using this app instance shares that key.")
    st.markdown("Use **your own** key from the Groq console. Usage is subject to your Groq account's limits, rate "
                "limits and any applicable pricing - free usage is not guaranteed.")

    st.subheader("Capability check (optional)")
    st.caption("Three tiny requests: connection, native tool calling and JSON mode - the features the agent needs.")
    if st.button("🧪 Run capability check"):
        key_now = active_api_key()
        if not key_now:
            st.error("No key available. Connect a key in the sidebar first, or use Demo Mode.")
        else:
            with st.spinner("Checking connection, tool calling and JSON mode..."):
                st.session_state["capability"] = run_capability_check(GroqLLM(key_now))
    cap = st.session_state.get("capability")
    if cap:
        st.dataframe([{"Check": k, "OK": "✅" if v["ok"] else "❌", "Detail": v["detail"]}
                      for k, v in cap.items() if isinstance(v, dict)], hide_index=True, width="stretch")

    st.subheader("Modes")
    st.markdown(f"""
| | **{config.MODE_LIVE}** (primary) | **{config.MODE_DEMO}** (fallback) |
|---|---|---|
| API key / internet | Your own Groq key | Not needed |
| Tool selection | `{config.LLM_MODEL}` via native tool calling | Deterministic rules |
| Root-cause hypothesis | Generated live by the model (JSON, validated) | **SIMULATED DEMO RESULTS** for the sample incidents; rule-based heuristic otherwise |
| Evidence verification | Deterministic checks **+** LLM reviewer | Deterministic checks |
| Log / YAML analysis | Real (deterministic code) | Real (deterministic code) |

If a live call fails (bad key, rate limit, network) the investigation **stops and explains why** and offers Demo
Mode - it never switches silently. You choose the mode in the sidebar.
""")
    st.subheader("Responsible AI and security")
    st.markdown("""
- Uploaded logs and documents are **untrusted data**; instructions inside them are ignored.
- The model can call only **allowlisted tools**; arguments are validated; tool calls and review rounds are capped.
- Facts (tool output), hypotheses (model or demo output) and recommendations are shown separately.
- Every production-changing action needs **human approval**, and even then it is only **simulated**.
- Kubernetes Secret values are masked and never stored. API keys are never stored or logged.
- Diagnoses may be wrong. Reflection reduces mistakes but does not guarantee correctness.
""")
    st.caption(f"Data directory: {config.DATA_DIR} · technical log: {config.LOG_DIR}")
