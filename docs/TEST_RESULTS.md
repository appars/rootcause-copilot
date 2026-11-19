# Test Results - RootCause Copilot v1.1 · Day 5 deployment-ready update

Recorded in the build environment on **2026-11-17**. Environment: Linux x86_64, Python 3.13.18, Streamlit 1.67.0,
groq SDK 1.7.0, Docker Engine 29.9.3, a virtual environment built from `requirements.txt` + `requirements-dev.txt`.
**Groq was mocked** in every automated test; no real API key was used.

Each result is labelled **PASSED**, **FAILED**, **NOT EXECUTED** (with the reason) or **MANUAL** (must be verified
on a real laptop/cluster). Nothing below is claimed beyond what was actually run.

## 1. Application

| Check | Command | Result |
|---|---|---|
| Unit + integration + Streamlit UI tests | `python -m pytest` | **PASSED** - 184 passed, 2 skipped (live Groq tests, need a key) |
| Byte-compile | `python -m compileall -q app.py config.py core memory tools ui scripts` | **PASSED** |
| Every module imports | CI import-check snippet | **PASSED** |
| Static analysis | `python -m pyflakes app.py config.py core memory tools ui scripts tests` | **PASSED** - no findings |
| Headless start (smoke) | `streamlit run app.py --server.headless true` → `/_stcore/health`, `/` | **PASSED** - `ok`, HTTP 200, no errors in the log |
| Demo Mode investigations INC-001…004, CHALLENGE-01 | `tests/test_orchestrator_demo.py` | **PASSED** (18 tests) |
| Configuration / data directory | `ROOTCAUSE_DATA_DIR` honoured (smoke test, container `/data`) | **PASSED** |
| SQLite persistence + migration | `tests/test_database.py`, `tests/test_v11_features.py` | **PASSED** |
| Live Groq call | `RUN_LIVE_TESTS=1 python -m pytest -m live` | **NOT EXECUTED** - no key in the build environment (by design) |

Tests per file: test_v11_features 60 · test_registry_context_reflection 21 · test_orchestrator_demo 18 ·
test_app_smoke 15 · test_security_and_docs 13 · test_deployment_artifacts 12 · test_orchestrator_live_fake 12 ·
test_uploads_and_documents 9 · test_database 8 · test_kubernetes_analyzer 8 · test_log_analyzer 6 ·
test_report_generator 2 · test_live_groq_optional 2 (skipped).

## 2. Docker

**Fidelity note.** Docker Hub and other public registries were blocked by the build environment's network policy
(`docker pull python:3.12-slim` → *Forbidden*). The image was therefore built with
`--build-arg PYTHON_IMAGE=local/python-standin:3.13` - a minimal local base assembled from the host's Python 3.13
(+ pip, glibc, libstdc++). Every Dockerfile instruction after `FROM` ran unchanged, including a real
`pip install -r requirements.txt` from PyPI. The image **size** and the exact base OS differ from the official
`python:3.12-slim`, so the default build must still be confirmed on a laptop or in GitHub Actions.

| Check | Result |
|---|---|
| `docker build` (stand-in base) | **PASSED** (~50 s; fixed `pip` → `python -m pip` during this test) |
| `docker build` with the default `python:3.12-slim` | **NOT EXECUTED** - registry blocked; runs in CI job `docker` |
| Image metadata: `User=10001`, `EXPOSE 8501`, `VOLUME /data`, `HEALTHCHECK` | **PASSED** |
| No proxy, key or `GROQ_API_KEY` in the image environment | **PASSED** |
| Image content: no `.env`, `tests/`, `.git`, `data_store/`, docs | **PASSED** (`/app` = app.py, config.py, core, data, memory, requirements.txt, tools, ui) |
| `docker run -p … -v …` → `(healthy)` | **PASSED** (healthy after ~9 s) |
| `/_stcore/health` = `ok`, `/` = HTTP 200 | **PASSED** |
| Runs as UID 10001, `/data` writable | **PASSED** |
| Full app render inside the container (Streamlit AppTest, UID 10001) | **PASSED** - no exceptions; sidebar `Release v1.1 · build latest` |
| Persistence: write incident → `docker restart` → still there | **PASSED** |
| Persistence: `docker rm -f` → new container, same volume → still there | **PASSED** (also survived a rebuild of the image) |
| Logs: no traceback, no key | **PASSED** |
| CI job `docker` steps executed verbatim (except the build step) | **PASSED** - run, health wait, security checks, persistence, logs |
| Multi-platform `buildx` (amd64 + arm64) and `docker push` | **NOT EXECUTED** - needs registry access and Docker Hub credentials · **MANUAL** |

Observation: a directory created from a `docker exec` session showed mode 777 because this environment's exec
sessions use umask 0000; the application process itself runs with umask 0022.

## 3. Kubernetes manifests

| Check | Result |
|---|---|
| Rendering equivalent to `kubectl kustomize kubernetes/` (resources-only Kustomization, test helper) | **PASSED** - Namespace, ConfigMap, PVC, Deployment, Service; no Secret |
| JSON-schema validation, Kubernetes v1.33 strict: rendered output (5) + `groq-secret.template` copy (1) | **PASSED** - 6/6 |
| References: ConfigMap name, `ROOTCAUSE_DATA_DIR` = mount path `/data`, PVC claim, Secret name/key, Service selector + `targetPort` | **PASSED** (`test_cross_references_resolve`) |
| Image `docker.io/DOCKERHUB_USERNAME/rootcause-copilot:latest` + `imagePullPolicy: Always` | **PASSED** |
| One namespace for all resources | **PASSED** |
| Probes (startup/readiness/liveness on `/_stcore/health`), resources, 1 replica, `Recreate` | **PASSED** |
| Security: `runAsNonRoot`, UID/GID/fsGroup 10001, seccomp, no privilege escalation, `drop: [ALL]`, no SA token | **PASSED** |
| PVC + Namespace `Prune=false,Delete=false` | **PASSED** |
| Project's own Kubernetes analyzer: 0 errors | **PASSED** (warning for `latest` is expected and documented) |
| CI "workshop rules" snippet on the rendered YAML | **PASSED** |
| Real `kubectl kustomize` / kubeconform | **NOT EXECUTED here** - kubectl not installed, downloads blocked; runs in CI job `manifests` |
| `kubectl apply -k`, pod Running, PVC Bound, port-forward, pod-deletion persistence | **NOT EXECUTED** - no cluster available · **MANUAL** (README_WINDOWS.md F, README_MAC.md F) |

## 4. ArgoCD

| Check | Result |
|---|---|
| `argocd/rootcause-copilot-application.yaml` against the upstream Argo CD `Application` CRD schema | **PASSED** |
| Single repository, `path: kubernetes`, `main`, in-cluster destination, `selfHeal: true`, `prune: false`, `CreateNamespace=true` | **PASSED** (`test_argocd_application_watches_this_repository`) |
| Install, login, sync, Synced/Healthy, self-heal, `git revert` rollback | **NOT EXECUTED** - no cluster · **MANUAL** |

## 5. CI workflows

| Check | Result |
|---|---|
| `ci.yml`, `docker-publish.yml` against GitHub's workflow JSON schema (`check-jsonschema`) | **PASSED** |
| All `run:` blocks parse (`bash -n`) | **PASSED** |
| `tests` job steps executed locally verbatim (Python 3.13) | **PASSED** |
| `docker` job steps executed locally (see §2) | **PASSED** |
| CI uses no secrets and never pushes; publish workflow manual-only | **PASSED** (`test_ci_workflows_are_safe`) |
| A real GitHub Actions run (Python 3.11 + 3.12, kubeconform, default base image) | **NOT EXECUTED** - nothing was pushed · **MANUAL**: push the branch and check the *Actions* tab |

## 6. Documentation

| Check | Result |
|---|---|
| Relative links **and `#anchors`** in every Markdown file | **PASSED** |
| Mermaid diagrams parse (mermaid + jsdom): README 5, README_WINDOWS 2, README_MAC 1, ARCHITECTURE 7, DOCKER 2, KUBERNETES 1, ARGOCD 2 | **PASSED** - 20/20 |
| Shell blocks: README_MAC (zsh), kubernetes/README, docker/README, README (bash) | **PASSED** with `bash -n` (zsh not installed - zsh-specific `read "VAR?prompt"` also parses in bash) |
| PowerShell blocks in README_WINDOWS.md / kubernetes/README.md | **MANUAL** - reviewed by reading only; PowerShell not available here |
| Required documents present; instructor material absent | **PASSED** |

## 7. Security

| Check | Result |
|---|---|
| Secret scan: `gsk_…` Groq keys, `dckr_pat_`, `ghp_`, `github_pat_` | **PASSED** - only the deliberate fake key in two test files |
| `.env`, databases not in the repository; `.env.example` placeholder only | **PASSED** |
| No Secret manifest in `kubernetes/` or `argocd/` | **PASSED** |

## 8. Still to verify manually (in this order)

1. GitHub Actions run on the pushed branch (all three jobs green).
2. Default `docker build` on a laptop (`python:3.12-slim`), image size, `docker push`, and, for the instructor,
   `docker buildx … --platform linux/amd64,linux/arm64 --push`.
3. Rancher Desktop: `kubectl apply -k kubernetes/` → Running/Bound → port-forward → pod-deletion persistence.
4. ArgoCD: install → Application → Synced/Healthy → `gitops-v2` → self-heal → `git revert`.
5. PowerShell commands of README_WINDOWS.md on a Windows 11 laptop.
