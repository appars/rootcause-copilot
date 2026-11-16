"""
RootCause Copilot - central configuration.

Provider and model are FIXED for the workshop. Students never choose them;
they only paste their own Groq API key in the Settings page.

All paths are resolved relative to this file, so the app works no matter
which folder you start Streamlit from (important on Windows).
"""
from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------
# Application identity
# --------------------------------------------------------------------------
APP_NAME = "RootCause Copilot"
APP_FULL_NAME = "RootCause Copilot \u2013 AI-Powered IT Operations Investigation Platform"
APP_TAGLINE = "AI-Powered IT Operations Investigation Platform (educational reference implementation)"
APP_RELEASE = "v1.1"
# Build/image tag baked into the container (shown in the sidebar; changes during the Day 5 GitOps demo).
APP_VERSION = os.getenv("ROOTCAUSE_APP_VERSION", "day4-v1")

# --------------------------------------------------------------------------
# LLM provider - fixed, read-only in the UI
# --------------------------------------------------------------------------
LLM_PROVIDER = "Groq"
LLM_MODEL = "openai/gpt-oss-20b"
GROQ_API_KEY_ENV = "GROQ_API_KEY"          # optional, e.g. from a Kubernetes Secret
LLM_TIMEOUT_SECONDS = 45.0
LLM_MAX_RETRIES = 2                         # retries for TRANSIENT errors only
LLM_BACKOFF_SECONDS = 1.5                   # 1.5s, 3s ... (exponential)
LLM_REASONING_EFFORT = "low"                # gpt-oss supports low / medium / high
LLM_MAX_OUTPUT_TOKENS = 1800

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
SAMPLE_DATA_DIR = BASE_DIR / "data"
SAMPLE_LOGS_DIR = SAMPLE_DATA_DIR / "sample_logs"
SAMPLE_DOCS_DIR = SAMPLE_DATA_DIR / "sample_documents"
SAMPLE_K8S_DIR = SAMPLE_DATA_DIR / "sample_kubernetes"
SCENARIOS_FILE = SAMPLE_DATA_DIR / "scenarios.json"
SEED_INCIDENTS_FILE = SAMPLE_DATA_DIR / "seed_incidents.json"
DEMO_RESULTS_FILE = SAMPLE_DATA_DIR / "demo" / "precomputed_results.json"

# Durable state lives here. Locally: ./data_store (git-ignored).
# In Kubernetes: ROOTCAUSE_DATA_DIR=/data, backed by a PersistentVolumeClaim.
DATA_DIR = Path(os.getenv("ROOTCAUSE_DATA_DIR", str(BASE_DIR / "data_store"))).resolve()
DB_PATH = Path(os.getenv("ROOTCAUSE_DB_PATH", str(DATA_DIR / "rootcause.db"))).resolve()

# --------------------------------------------------------------------------
# Upload limits (uploads are UNTRUSTED input)
# --------------------------------------------------------------------------
MAX_UPLOAD_BYTES = int(os.getenv("ROOTCAUSE_MAX_UPLOAD_BYTES", str(2 * 1024 * 1024)))  # 2 MB
ALLOWED_LOG_EXTENSIONS = {".log", ".txt"}
ALLOWED_DOC_EXTENSIONS = {".txt", ".md", ".log", ".pdf"}
ALLOWED_YAML_EXTENSIONS = {".yaml", ".yml"}

# --------------------------------------------------------------------------
# Agent safety limits (prevent unbounded loops / cost)
# --------------------------------------------------------------------------
MAX_TOOL_CALLS = 8
MAX_AGENT_TURNS = 10            # max LLM turns in the tool-selection loop
MAX_REFLECTION_ROUNDS = 2
MAX_CONTEXT_CHARS = 9000          # rough budget for evidence sent to the LLM
MAX_LOG_LINES_IN_CONTEXT = 40
MAX_SIMILAR_INCIDENTS = 3
MAX_KB_SNIPPETS = 3
TOOL_RESULT_MAX_CHARS = 2500      # each tool result is truncated before reaching the LLM

# --------------------------------------------------------------------------
# Modes
# --------------------------------------------------------------------------
MODE_DEMO = "Demo Mode"
MODE_LIVE = "Live AI Mode"
DEMO_LABEL = "SIMULATED DEMO RESULTS - predefined output; no live AI reasoning was performed"

# Services offered in the New Investigation form ("Other" lets users type a name).
KNOWN_SERVICES = ["payment-service", "order-service", "inventory-service", "notification-service",
                  "search-service", "api-gateway"]

# Knowledge-base relevance filter: a chunk must share at least this many meaningful terms
# with the query, otherwise it is NOT injected into the LLM context.
KB_MIN_MATCHED_TERMS = 2

# Technical log file (no API keys - a redaction filter is applied). Lives next to the database.
LOG_DIR = Path(os.getenv("ROOTCAUSE_LOG_DIR", str(DATA_DIR / "logs"))).resolve()
