"""Kubernetes Configuration Analyzer page (static checks, secrets masked)."""
from __future__ import annotations

import streamlit as st

import config
from tools.kubernetes_analyzer import STATIC_NOTE, YamlParseError, analyze_kubernetes_yaml
from tools.uploads import UploadError, decode_text, validate_upload


def render() -> None:
    st.title("☸️ Kubernetes Configuration Analyzer")
    st.warning(STATIC_NOTE + " Secret values are always masked and never stored.")
    samples = sorted(p.name for p in config.SAMPLE_K8S_DIR.glob("*.y*ml"))
    c1, c2 = st.columns(2)
    sample = c1.selectbox("Load a synthetic sample", [""] + samples, format_func=lambda s: s or "(none)")
    upload = c2.file_uploader("...or upload YAML", type=["yaml", "yml"])
    text = st.text_area("...or paste YAML", height=220,
                        value=(config.SAMPLE_K8S_DIR / sample).read_text(encoding="utf-8") if sample else "")
    if st.button("Analyze", type="primary"):
        try:
            if upload is not None:
                data = upload.getvalue()
                validate_upload(upload.name, data, config.ALLOWED_YAML_EXTENSIONS)
                text = decode_text(upload.name, data)
            result = analyze_kubernetes_yaml(text)
        except (YamlParseError, UploadError) as e:
            st.error(f"Could not analyse the YAML: {e}")
            return
        c = result["counts"]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Resources", len(result["resources"]))
        m2.metric("Errors", c["error"])
        m3.metric("Warnings", c["warning"])
        m4.metric("Info", c["info"])
        st.subheader("Resources")
        st.dataframe(result["resources"], hide_index=True, width="stretch")
        st.subheader("Findings - deterministic validation")
        st.caption("Produced by rule-based checks in tools/kubernetes_analyzer.py - not by an LLM.")
        if result["findings"]:
            st.dataframe([{"Severity": f["severity"], "Finding": f["message"], "Affected resource": f["resource"],
                           "Evidence": f.get("evidence", "-"), "Recommended correction": f.get("recommendation", "-"),
                           "Why it matters": f["explanation"]} for f in result["findings"]],
                         hide_index=True, width="stretch")
        else:
            st.success("No issues found by the static checks.")
        with st.expander("YAML as analysed (Secret values masked)"):
            st.code(result["masked_yaml"], language="yaml")
