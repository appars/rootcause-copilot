"""Knowledge Base page - add and inspect runbooks / incident reports / documents."""
from __future__ import annotations

import streamlit as st

from memory import document_repository
from tools.document_search import ingest_document, ingest_sample_documents, search_knowledge_base


def render() -> None:
    st.title("📖 Knowledge Base")
    st.markdown("Runbooks and reports the agent can search with the `search_knowledge_base` tool. Supported: "
                "`.txt`, `.md`, `.log`, `.pdf` (max 2 MB). Documents are treated as **untrusted data** - "
                "instructions inside them are never followed. A document is only marked *indexed* if text was "
                "actually extracted.")
    c1, c2 = st.columns([1, 2])
    if c1.button("📥 Load bundled sample documents"):
        res = ingest_sample_documents()
        if res:
            for r in res:
                (st.success if r["status"] == "indexed" else st.error)(f"{r['filename']}: {r['message']}")
        else:
            st.info("Sample documents are already loaded.")
    uploads = c2.file_uploader("Upload documents", type=["txt", "md", "log", "pdf"], accept_multiple_files=True)
    if uploads and st.button("Index uploaded files"):
        for f in uploads:
            r = ingest_document(f.name, f.getvalue())
            (st.success if r["status"] == "indexed" else st.error)(f"{r['filename']}: {r['message']}")

    docs = document_repository.list_documents()
    st.subheader("Documents")
    if not docs:
        st.info("No documents yet. Click **Load bundled sample documents**.")
    else:
        st.dataframe([{"ID": d["id"], "File": d["filename"], "Type": d["doc_type"], "Status": d["status"],
                       "Chunks": d["chunks"], "Characters": d["chars"], "Note": d["note"] or "-",
                       "Added (UTC)": d["created_at"]} for d in docs], hide_index=True, width="stretch")
        indexed = [d for d in docs if d["status"] == "indexed"]
        if indexed:
            pick = st.selectbox("Inspect extracted text", [d["id"] for d in indexed],
                                format_func=lambda i: next(d["filename"] for d in indexed if d["id"] == i))
            with st.expander("Extracted text"):
                st.text(document_repository.get_document_text(pick)[:6000])

    st.subheader("Try a search")
    q = st.text_input("Query", placeholder="connection pool timeout runbook")
    if q:
        hits = search_knowledge_base(q, top_k=5)
        if not hits:
            st.info("No matches.")
        for h in hits:
            with st.expander(f"{h['filename']} · chunk {h['chunk']} · score {h['score']} · terms: {', '.join(h['matched_terms'])}"):
                st.text(h["snippet"])
