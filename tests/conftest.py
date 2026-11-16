"""Shared test fixtures.

ROOTCAUSE_DATA_DIR is pointed at a temporary folder BEFORE config is imported,
so tests never touch a developer's real data_store/.
"""
import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="rootcause_test_")
os.environ["ROOTCAUSE_DATA_DIR"] = _TMP
if os.getenv("RUN_LIVE_TESTS") != "1":
    os.environ.pop("GROQ_API_KEY", None)   # normal test runs never use a real key
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from memory.database import init_db  # noqa: E402


@pytest.fixture()
def db(tmp_path):
    """A fresh, seeded SQLite database for one test."""
    path = tmp_path / "test.db"
    init_db(path)
    return path


@pytest.fixture()
def no_sleep():
    return lambda seconds: None
