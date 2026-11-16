"""Investigation Reports page - view and download past reports."""
from __future__ import annotations

import streamlit as st

from memory import incident_repository
from tools.report_generator import markdown_to_pdf


def render() -> None:
    st.title("📄 Investigation Reports")
    reports = incident_repository.list_reports()
    if not reports:
        st.info("No reports yet. Reports are generated automatically at the end of every investigation.")
        return
    latest: dict[str, dict] = {}
    for r in reports:                       # newest first -> keep the first per incident
        latest.setdefault(r["incident_id"], r)
    show_all = st.checkbox("Show every report version", value=False)
    items = reports if show_all else list(latest.values())
    st.dataframe([{"Report #": r["id"], "Incident": r["incident_id"], "Title": r["title"], "Service": r["service"],
                   "Severity": r["severity"], "Created (UTC)": r["created_at"]} for r in items],
                 hide_index=True, width="stretch")
    pick = st.selectbox("Open report", [r["id"] for r in items],
                        format_func=lambda i: next(f"#{r['id']} - {r['incident_id']} {r['title']}" for r in items if r["id"] == i))
    rep = incident_repository.get_report(pick)
    if rep:
        c1, c2 = st.columns(2)
        c1.download_button("⬇ Markdown", rep["markdown"], file_name=f"{rep['incident_id']}_report_{rep['id']}.md",
                           mime="text/markdown")
        c2.download_button("⬇ PDF", markdown_to_pdf(rep["markdown"]),
                           file_name=f"{rep['incident_id']}_report_{rep['id']}.pdf", mime="application/pdf")
        with st.container(border=True):
            st.markdown(rep["markdown"])
