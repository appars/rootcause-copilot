"""RootCause Copilot \u2013 AI-Powered IT Operations Investigation Platform (v1.1) - Streamlit entry point.

Run from the repository root:
    python -m streamlit run app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Make "import config", "import core..." work regardless of the current folder.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
from memory.database import DatabaseError, init_db  # noqa: E402
from ui import dashboard, history, investigation, knowledge_base, kubernetes, reports, settings  # noqa: E402
from core.logging_setup import get_logger  # noqa: E402
from ui.common import CSS, init_session, sidebar_ai_configuration, sidebar_mode_selector  # noqa: E402

log = get_logger("rootcause.app")

PAGES = {
    "Dashboard": dashboard.render,
    "New Investigation": investigation.render,
    "Incident History": history.render,
    "Knowledge Base": knowledge_base.render,
    "Kubernetes Analyzer": kubernetes.render,
    "Investigation Reports": reports.render,
    "Settings": settings.render,
}


@st.cache_resource(show_spinner=False)
def _initialise_database() -> str:
    return str(init_db())


def main() -> None:
    st.set_page_config(page_title=f"{config.APP_NAME} {config.APP_RELEASE}", page_icon="🛠️", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    init_session()
    try:
        _initialise_database()
    except DatabaseError:
        log.exception("Database initialisation failed")
        st.error(f"The incident database could not be opened at `{config.DATA_DIR}`. Check that the folder exists "
                 "and is writable (avoid read-only or locked cloud-sync folders), or set ROOTCAUSE_DATA_DIR to "
                 "another folder. See docs/TROUBLESHOOTING.md.")
        st.stop()

    st.sidebar.markdown(f"## 🛠️ {config.APP_NAME}")
    st.sidebar.caption("AI-Powered IT Operations Investigation Platform · educational & simulated")
    page = st.sidebar.radio("Navigate", list(PAGES), key="page")
    st.sidebar.divider()
    sidebar_ai_configuration()
    st.sidebar.divider()
    sidebar_mode_selector()
    st.sidebar.divider()
    st.sidebar.caption(f"Release {config.APP_RELEASE} · build {config.APP_VERSION}")
    try:
        PAGES[page]()
    except Exception:  # noqa: BLE001 - students see a friendly message, the log gets the details
        log.exception("Unhandled error on page %s", page)
        st.error("Something went wrong on this page. The technical details were written to the application log "
                 "(API keys are never logged). Your saved investigations are not affected - try again or open "
                 "another page.")


main()
