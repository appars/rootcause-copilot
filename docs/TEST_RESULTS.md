# Test Results - RootCause Copilot v1.1

Recorded in the build environment on 2026-11-16. Environment: Linux, Python 3.13.18, Streamlit 1.67.0,
groq SDK 1.7.0, a fresh virtual environment built from `requirements.txt` + `requirements-dev.txt`.
**Groq was mocked** in every automated test. No real API key was used.

## 1. Executed and passed

| Check | Command | Result |
|---|---|---|
| Unit + integration + UI tests | `python -m pytest` | **178 passed, 2 skipped** (≈6 s) |
| Static analysis | `python -m pyflakes .` | no findings |
| Byte-compile | `python -m compileall -q .` | OK |
| Headless app start | `streamlit run app.py --server.headless true` | `/_stcore/health` → 200, `/` → 200, no errors in the log |
| Kubernetes manifests | JSON-schema validation (Kubernetes v1.33, strict): `kubernetes/`, GitOps `apps/rootcause-copilot/`, `data/sample_kubernetes/`, and `groq-secret.template` (as a copy) | **29/29 passed** |
| ArgoCD Application | Validated against the upstream Argo CD `Application` CRD schema (app repo + GitOps repo copies) | **2/2 passed** |
| Mermaid diagrams | Parsed with mermaid (jsdom): `ARCHITECTURE.md` ×7, `README.md` ×1 | **8/8 passed** |
| Secret scan | regex `gsk_[A-Za-z0-9]{20,}` over the app, GitOps and instructor folders | no matches |
| GitOps copy | `kubernetes/` vs GitOps `apps/rootcause-copilot/` | identical except README + secret template (intended) |
| Release ZIP | Extracted to a clean folder; full test suite re-run from the extracted copy | see §5 |

### What the test suite covers (by file)

| File | Tests | Focus |
|---|---|---|
| test_v11_features.py | 60 | trace statuses/origins/durations, evidence labels, error-pattern analyzer, new K8s checks, log redaction, filename sanitising, DB migration, risk levels, KB relevance, challenge scenario |
| test_registry_context_reflection.py | 21 | tool allow-list, context budget, prompt-injection flags, reflection rounds (max 2) |
| test_orchestrator_demo.py | 18 | full Demo Mode investigations INC-001…004 + CHALLENGE-01, memory write-back, approval/audit |
| test_app_smoke.py | 15 | Streamlit `AppTest`: every page renders, and the sidebar Connect / Test / Clear flows (mocked) never display the full key |
| test_security_and_docs.py | 13 | no secrets or DBs shipped, `.gitignore`, links resolve, required docs, instructor files absent, ≥7 Mermaid diagrams, challenge without a demo answer |
| test_orchestrator_live_fake.py | 12 | Live AI path with a fake Groq client: tool calls, invalid JSON retry, auth / 429 / timeout handling, no silent switch to Demo Mode |
| others | 39 | database, log analyzer, K8s analyzer, uploads/documents, reports (15 sections), deployment artifacts |

## 2. Failed

None in the final run.

## 3. Skipped / not executed

| Item | Why |
|---|---|
| `tests/test_live_groq_optional.py` (2 tests) | Needs `GROQ_API_KEY` and `RUN_LIVE_TESTS=1`. The build environment cannot reach `api.groq.com`. |
| Real Groq connection, tool calling and JSON mode with `openai/gpt-oss-20b` | **Not verified.** Run *Settings → Run capability check* with a real key before class. |
| `docker build` / `docker run` / push to Docker Hub | No container runtime, and Docker Hub is not reachable from the build environment. |
| Kubernetes deployment (pods, PVC binding, probes, port-forward) | No cluster available. Only the schema validation in §1 was done. |
| ArgoCD install, sync, self-heal, rollback | No cluster available. |
| Windows 10/11 run (PowerShell, `py` launcher, paths) | Built and tested on Linux only. The code uses `pathlib` and the docs give PowerShell commands, but this was not executed on Windows. |
| macOS + Rancher Desktop (dockerd and containerd) | Not available. |

## 4. Instructor pre-class verification (do this yourself)

- [ ] Windows: create a venv, `pip install -r requirements.txt`, `python -m pytest`, then `streamlit run app.py`.
- [ ] Sidebar → Connect with a real Groq key → 🟢; *Settings → Run capability check* is all green.
- [ ] Run INC-001 in Live AI Mode; check the trace, the evidence labels and the report download.
- [ ] Mac: `docker build`, `docker run`, push and pull back; `kubectl apply -k kubernetes/`; full ArgoCD flow (Day 5 guide).

## 5. Release package check

`RootCause_Copilot_Workshop_v1.1.zip` was extracted to an empty folder. The test suite was re-run there with the
same result as §1. The archive contains no `.env`, `*.db`, `data_store/`, `__pycache__`, `.pytest_cache`,
virtual environments or real keys.
