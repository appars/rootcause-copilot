"""Incident History page - browse and search persistent memory (SQLite)."""
from __future__ import annotations

import streamlit as st

from memory import audit_repository, incident_repository
from tools.incident_retriever import retrieve_similar_incidents
from ui.common import render_timeline, severity_badge, status_badge


def render() -> None:
    st.title("📚 Incident History")
    st.markdown("This is the agent's **persistent incident memory**. It is stored in SQLite on disk, so it survives "
                "an app restart - unlike short-term session state. Records with source *seed* are **fictional sample "
                "history** shipped with the workshop; everything else was created by investigations in this app.")
    c1, c2, c3 = st.columns([3, 2, 1])
    search = c1.text_input("Search (title, symptoms, root cause, lessons...)", placeholder="connection pool")
    services = sorted({i["service"] for i in incident_repository.list_incidents(limit=1000)})
    service = c2.selectbox("Service", [""] + services, format_func=lambda s: s or "All services")
    include_seed = c3.checkbox("Include seed", value=True)
    rows = incident_repository.list_incidents(search=search, service=service, include_seed=include_seed)
    if not rows:
        st.info("No incidents match.")
    else:
        st.dataframe([{"ID": r["id"], "Date": r["created_at"][:10], "Service": r["service"], "Severity": r["severity"],
                       "Status": r["status"], "Source": r["source"], "Title": r["title"],
                       "Root cause": (r["root_cause"] or "-")[:120]} for r in rows], hide_index=True, width="stretch")
        chosen = st.selectbox("Open incident", [r["id"] for r in rows])
        inc = incident_repository.get_incident(chosen)
        if inc:
            with st.container(border=True):
                st.markdown(f"### {inc['id']} - {inc['title']}")
                st.markdown(severity_badge(inc["severity"]) + status_badge(inc["status"]) +
                            f"<span class='rc-muted'>{inc['service']} · {inc['created_at']}</span>", unsafe_allow_html=True)
                st.markdown(f"**Symptoms:** {inc['symptoms'] or '-'}")
                st.markdown(f"**Log patterns:** {', '.join(inc['log_patterns']) or '-'}")
                st.markdown(f"**Hypothesis:** {inc['hypothesis'] or '-'}")
                if inc.get("evidence_assessment"):
                    st.markdown(f"**Evidence assessment:** {inc['evidence_assessment']}")
                if inc.get("supporting_evidence"):
                    st.markdown("**Supporting evidence:**\n" + "\n".join(f"- {e}" for e in inc["supporting_evidence"]))
                if inc.get("recommended_actions"):
                    st.markdown(f"**Recommended actions:** {inc['recommended_actions']}")
                st.markdown(f"**Root cause:** {inc['root_cause'] or '_not confirmed_'}")
                st.markdown(f"**Resolution:** {inc['resolution'] or '-'}")
                st.markdown(f"**Lessons learned:** {inc['lessons_learned'] or '-'}")
                st.caption(f"Investigation mode: {inc['mode'] or '-'} · created {inc['created_at']} · "
                           f"updated {inc['updated_at']} · source: {inc['source']}")
                tl = incident_repository.get_timeline(inc["id"])
                if tl:
                    with st.expander("Timeline"):
                        render_timeline(tl)
                audit = audit_repository.list_audit_records(inc["id"])
                if audit:
                    with st.expander("Approval / audit records"):
                        st.dataframe(audit, hide_index=True, width="stretch")

    st.subheader("Find similar incidents")
    q = st.text_input("Describe the symptoms", placeholder="checkout 503 connection is not available pool idle=0")
    svc = st.text_input("Service (optional)", placeholder="payment-service")
    if q:
        hits = retrieve_similar_incidents(q, service=svc.strip(), top_k=5)
        if not hits:
            st.info("No similar incidents with a known outcome were found.")
        for h in hits:
            st.markdown(f"- **{h['id']}** ({h['service']}, score {h['score']}): {h['title']} - "
                        f"*{h['root_cause'][:160]}*  \n  matched on: {', '.join(h['matched_on'])}")
        st.caption("Scoring: 0.45 keyword overlap + 0.35 log-pattern overlap + 0.20 same service "
                   "(see tools/incident_retriever.py).")
    st.download_button("⬇ Export incident history (JSON)", incident_repository.export_history(),
                       file_name="rootcause_incident_history.json", mime="application/json")
