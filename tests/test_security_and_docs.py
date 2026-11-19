"""Repository hygiene: no committed secrets, .gitignore coverage, documentation links resolve."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEXT_EXT = {".py", ".md", ".yaml", ".yml", ".json", ".txt", ".toml", ".example", ".ini", ""}
# Groq keys start with "gsk_". The test file that uses a FAKE key is excluded explicitly.
KEY_RE = re.compile(r"gsk_[A-Za-z0-9]{20,}")
ALLOWED_FAKE = {"test_orchestrator_live_fake.py", "test_security_and_docs.py"}


def _files(base: Path):
    for p in base.rglob("*"):
        if p.is_file() and not any(part in {".venv", "__pycache__", ".pytest_cache", "data_store", ".git"} for part in p.parts):
            yield p


def test_no_real_looking_api_keys_committed():
    hits = []
    for base in (ROOT,):
        for p in _files(base):
            if p.suffix in TEXT_EXT and p.name not in ALLOWED_FAKE:
                text = p.read_text(encoding="utf-8", errors="ignore")
                if KEY_RE.search(text):
                    hits.append(str(p))
    assert hits == []


def test_no_env_file_or_database_shipped():
    assert not (ROOT / ".env").exists()
    assert not list(ROOT.glob("*.db"))


def test_env_example_has_placeholder_only():
    text = (ROOT / ".env.example").read_text()
    assert "GROQ_API_KEY=your_groq_api_key_here" in text


def test_gitignore_covers_secrets_and_state():
    gi = (ROOT / ".gitignore").read_text().splitlines()
    for entry in (".env", "data_store/", "*.db", ".venv/", "*.secret.yaml", ".streamlit/secrets.toml"):
        assert entry in gi


def test_no_secret_manifests_in_deployment_folders():
    for folder in (ROOT / "kubernetes", ROOT / "argocd"):
        if folder.exists():
            for f in folder.rglob("*.yaml"):
                assert "kind: Secret" not in f.read_text(), f


def test_markdown_relative_links_resolve():
    link = re.compile(r"\]\((?!https?://|#|mailto:)([^)\s#]+)")
    broken = []
    for md in ROOT.rglob("*.md"):
        if any(part in {".venv", ".pytest_cache"} for part in md.parts):
            continue
        for target in link.findall(md.read_text(encoding="utf-8")):
            if not (md.parent / target).exists():
                broken.append(f"{md.relative_to(ROOT)} -> {target}")
    assert broken == []


def test_required_documents_exist():
    for name in ("DAY4_HANDS_ON_GUIDE.md", "DAY4_STUDENT_WORKSHEET.md", "DAY5_MAC_INSTRUCTOR_GUIDE.md",
                 "DAY5_WINDOWS_DEPLOYMENT_HOMEWORK.md", "TROUBLESHOOTING.md", "HOMEWORK_SUBMISSION.md",
                 "TEST_RESULTS.md"):
        assert (ROOT / "docs" / name).exists(), name
    for name in ("DOCKER_DEPLOYMENT.md", "KUBERNETES_DEPLOYMENT.md", "ARGOCD_GITOPS.md"):
        assert (ROOT / "docs" / name).exists(), name
    for name in ("README.md", "README_WINDOWS.md", "README_MAC.md", "ARCHITECTURE.md", "SECURITY.md",
                 "RELEASE_NOTES.md", ".env.example"):
        assert (ROOT / name).exists(), name


def test_instructor_material_not_in_student_repository():
    names = {p.name for p in _files(ROOT)}
    for forbidden in ("INSTRUCTOR_ANSWER_KEY.md", "INSTRUCTOR_NOTES.md", "DEMO_SCRIPT.md"):
        assert forbidden not in names, forbidden


def test_architecture_has_seven_mermaid_diagrams():
    text = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    assert text.count("```mermaid") >= 7


def test_homework_has_day4_challenge_part():
    text = (ROOT / "docs" / "HOMEWORK_SUBMISSION.md").read_text(encoding="utf-8")
    assert "## Part A - Day 4 mini challenge" in text and "## Part B - Day 5 deployment homework" in text


def test_challenge_has_no_predefined_demo_answer():
    import json
    scenarios = json.loads((ROOT / "data" / "scenarios.json").read_text(encoding="utf-8"))
    items = scenarios if isinstance(scenarios, list) else scenarios.get("scenarios", scenarios)
    challenge_ids = [s["id"] for s in items if isinstance(s, dict) and s.get("challenge")]
    assert challenge_ids, "challenge scenario missing"
    demo_files = list((ROOT / "data" / "demo").glob("*.json"))
    assert demo_files, "demo results file not found"
    for f in demo_files:
        for cid in challenge_ids:
            assert cid not in f.read_text(encoding="utf-8"), f"{cid} has a predefined demo answer in {f.name}"


def test_secret_template_has_placeholder_only():
    text = (ROOT / "kubernetes" / "groq-secret.template").read_text(encoding="utf-8")
    assert "REPLACE_WITH_YOUR_GROQ_API_KEY" in text and not KEY_RE.search(text)
    kust = (ROOT / "kubernetes" / "kustomization.yaml").read_text(encoding="utf-8")
    assert "groq-secret" not in kust


def test_answer_key_not_in_student_sample_data():
    # Logs must give evidence, not announce the root cause.
    for log in (ROOT / "data" / "sample_logs").glob("*.log"):
        text = log.read_text().lower()
        assert "root cause" not in text and "connection pool exhausted" not in text
