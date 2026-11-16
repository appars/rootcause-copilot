"""Dashboard page: purpose, status, metrics and recent incidents."""
from __future__ import annotations

import pandas as pd
import streamlit as st

import config
from memory import document_repository, incident_repository
from ui.common import connection_indicator, mode_banner, severity_badge, status_badge

CONCEPT_MAP = [
    ("1. Persistent memory", "History page; 'Similar incidents' tab; restart the app and the history is still there", "memory/, tools/incident_retriever.py"),
    ("2. Context management", "'Context & memory' tab: what was included, collapsed, truncated or excluded - and the three kinds of memory", "core/context_manager.py"),
    ("3. Dynamic decision-making", "'Execution trace' + 'Agent actions' tabs: which tools ran or were skipped, and why", "core/agent.py, core/tool_registry.py, core/trace.py"),
    ("4. Event-driven execution", "'Simulate New Incident Alert' button; trace starts with 'Incident Received' (SIMULATED alert)", "core/event_handler.py"),
    ("5. Self-reflection", "'Diagnosis & evidence' tab: initial vs revised hypothesis, evidence labels, reviewer checks", "core/reflection.py"),
    ("6. Error recovery", "Instructor failure simulation; retries/degraded steps in the timeline; error samples", "core/tool_executor.py, core/llm_client.py"),
    ("7. Human approval", "'Approval' tab: approve / reject / request more info; audit trail", "core/approval.py, memory/audit_repository.py"),
]


def render() -> None:
    st.title(f"🛠️ {config.APP_FULL_NAME}")
    st.caption(f"{config.APP_RELEASE} · {config.APP_TAGLINE}")
    mode_banner()
    st.info("**Educational reference implementation.** All incidents, logs and actions are synthetic or simulated. "
            "RootCause Copilot does not connect to Prometheus, Kubernetes clusters, payment systems or any real "
            "infrastructure, and it never executes production changes.")

    counts = incident_repository.incident_counts()
    docs = [d for d in document_repository.list_documents() if d["status"] == "indexed"]
    seed_count = counts["memory_records"] - counts["investigations"]
    st.markdown("##### Your investigations (created in this app)")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total investigations", counts["investigations"])
    c2.metric("Open", counts["open"], help="open, investigating or awaiting approval")
    c3.metric("Resolved", counts["completed"], help="mitigated (simulated action approved) or closed")
    c4.metric("Knowledge-base documents", len(docs))
    st.caption(f"Memory also holds **{seed_count} fictional historical incidents** (sample data, labelled 'seed') - "
               "they are not counted above.")

    s1, s2 = st.columns(2)
    s1.markdown(f"**Mode:** {st.session_state['mode']}")
    s2.markdown(f"**AI:** {config.LLM_PROVIDER} · `{config.LLM_MODEL}` · {connection_indicator()}")

    dist = incident_repository.distribution()
    if counts["investigations"]:
        d1, d2 = st.columns(2)
        with d1:
            st.markdown("**Investigations by severity**")
            st.bar_chart(pd.DataFrame({"investigations": dist["severity"]}), height=220)
        with d2:
            st.markdown("**Investigations by service**")
            st.bar_chart(pd.DataFrame({"investigations": dist["service"]}), height=220)

    st.subheader("Recently investigated incidents")
    recent = incident_repository.list_incidents(include_seed=False, limit=8)
    if not recent:
        st.caption("No investigations yet. Go to **New Investigation** and click **Simulate New Incident Alert**.")
    for inc in recent:
        st.markdown(f"{severity_badge(inc['severity'])}{status_badge(inc['status'])} **{inc['id']}** - "
                    f"{inc['title']} <span class='rc-muted'>({inc['service']}, {inc['created_at'][:16]} UTC, "
                    f"{inc['mode'] or '-'})</span>", unsafe_allow_html=True)

    st.subheader("Where to observe the seven Day 4 concepts")
    st.dataframe([{"Concept": c, "Where in the app": w, "Code": m} for c, w, m in CONCEPT_MAP],
                 hide_index=True, width="stretch")
    st.caption(f"Data directory: `{config.DATA_DIR}` (SQLite: `{config.DB_PATH.name}`). "
               f"Release {config.APP_RELEASE}, build {config.APP_VERSION}.")
