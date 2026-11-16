# Security and Responsible AI - RootCause Copilot v1.1

RootCause Copilot is an **educational reference implementation** running in a **simulated** environment. It is
**not** production-certified and **not** production-secure. This document lists the safeguards it implements and
the limitations it does not pretend to overcome.

## 1. API key handling

| Rule | How it is implemented |
|---|---|
| Never hardcoded | No key in code, config, tests or images; `.env.example` holds a placeholder only |
| Entered by the student | Sidebar **AI Configuration** password field (`ui/common.sidebar_ai_configuration`) |
| Kept in server-side session memory only | `st.session_state["groq_api_key"]`; gone on browser refresh, app restart or **Clear API key** |
| Never shown in full again | UI shows `••••••••` + last 4 characters only |
| Never stored in SQLite / reports / files | Automated test checks the database file and the result for a test key |
| Never logged | `core/logging_setup.RedactingFilter` removes `gsk_…` patterns, `api_key=` / `Authorization` values and the registered session key from every log record, including tracebacks |
| Real verification | *Connect / Test connection* retrieves the fixed model's metadata from Groq; success is shown only if Groq accepts the key **and** the model is accessible |
| Kubernetes | optional Secret `rootcause-groq` → env `GROQ_API_KEY` (`optional: true`); created with `kubectl`, never committed |

A server-side key (Kubernetes Secret) is shared by **everyone** who can open that app instance. Groq usage is
subject to the account's limits, rate limits and applicable pricing; free usage is not guaranteed.

## 2. Secret management (Day 5)

- Recommended: `kubectl create secret generic rootcause-groq ...` with the value read from a hidden prompt
  (commands in `kubernetes/README.md`). The value never touches a file.
- File option: `kubernetes/groq-secret.template` → copy to `kubernetes/groq.secret.yaml` (git-ignored pattern
  `*.secret.yaml`), apply, delete the copy.
- The GitOps repository contains **no** Secret; `.gitignore` files in both repositories block common secret files.
- base64 in a Secret is encoding, not encryption. Never project `kubectl get secret -o yaml`.
- Production: use a secret manager (External Secrets Operator, Sealed Secrets, cloud KMS) - out of scope here.

## 3. File and input validation

- Extension allowlists: logs `.log/.txt`; documents `.txt/.md/.log/.pdf`; YAML `.yaml/.yml`.
- Size limit 2 MB (application check **and** Streamlit `server.maxUploadSize = 2`).
- Empty and binary files are rejected; PDFs are parsed with `pypdf`; corrupt, encrypted or image-only PDFs are
  recorded as **failed** - never as indexed.
- Filenames are sanitised (`tools/uploads.sanitize_filename`): path components removed, unusual characters replaced,
  length limited.
- YAML is parsed with `yaml.safe_load_all` (no object construction / code execution).
- Form fields have maximum lengths; all SQL uses parameterised queries (column names only from allowlists).
- Uploaded content and the optional "context" field are wrapped in `<untrusted_evidence>` before reaching the model;
  injection-like text ("ignore all previous instructions…") is flagged in the *Context & memory* tab.
  Detection is heuristic: it reduces risk but cannot guarantee a model is never influenced.

## 4. Bounded, non-executing agent

- The model can only request five allowlisted, read-only tools; arguments are validated against explicit schemas.
- No shell, file-system, network or infrastructure tool exists. Model output is never executed.
- Limits: 8 tool calls, 10 model turns, 2 reflection rounds, context budget, truncated tool results,
  45 s timeout, 2 retries for transient errors only (no retry for invalid key / bad request / unknown model).
- Every production-changing action - and any unrecognised action type - requires human approval, and even an
  approved action is only **simulated** (the audit trail records the command that *would* run).
- A Streamlit button is **not** enterprise authorisation: no SSO, RBAC, four-eyes rule or immutable audit store.

## 5. Honest output

- Facts (tool output), hypotheses (model or demo output) and recommendations are shown separately.
- Evidence is labelled *Strong supporting / Partial supporting / Contradictory / Insufficient*; no invented
  percentages. Reflection reduces mistakes but does not guarantee correctness.
- Demo Mode output is always labelled **SIMULATED DEMO RESULTS**; the execution trace marks each step's origin.
- Live failures stop the investigation with an explanation and an *offer* of Demo Mode - never a silent switch.
- Hidden model reasoning is never requested for display or shown.

## 6. Error handling and logging

- Students see friendly, actionable messages; Streamlit `client.showErrorDetails = "none"` and a page-level error
  boundary in `app.py` keep stack traces off the screen.
- Technical details go to `$ROOTCAUSE_DATA_DIR/logs/app.log` (rotating, 1 MB × 3), redacted; if that folder is
  not writable, logging falls back to stderr.
- One failing investigation is contained (status `failed`, trace step marked *Failed*); the app keeps running.

## 7. Container security

| Control | Where |
|---|---|
| Slim base image `python:3.12-slim`, runtime dependencies only (no pytest) | `Dockerfile` |
| Non-root user `10001`, `HOME=/tmp`, owns only `/data` | `Dockerfile` |
| `.dockerignore` excludes `.env`, databases, venvs, tests, docs | `.dockerignore` |
| No key in the image; versioned tags (`day4-v1`), never only `latest` | Dockerfile + manifests |
| `runAsNonRoot`, `fsGroup`, `seccompProfile: RuntimeDefault` | `kubernetes/deployment.yaml` |
| `allowPrivilegeEscalation: false`, all Linux capabilities dropped | `kubernetes/deployment.yaml` |
| `automountServiceAccountToken: false` (the app never calls the Kubernetes API) | `kubernetes/deployment.yaml` |
| Only port 8501 exposed; ClusterIP Service + `kubectl port-forward` (no public ingress) | `service.yaml` |
| PVC protected from ArgoCD pruning (`Prune=false` annotation) | `kubernetes/pvc.yaml` |

`readOnlyRootFilesystem` is **not** enabled because it has not been tested with Streamlit in this build; it is a
good next hardening step after testing.

## 8. Known limitations

- No authentication, authorisation or multi-user isolation - run locally or on a trusted network only.
- Single SQLite file, one replica - not highly available, not multi-writer.
- Heuristic log parsing and keyword retrieval can miss evidence; static YAML checks cannot prove cluster health.
- No real monitoring webhook. A production webhook would need authentication (HMAC/mTLS), rate limiting and replay
  protection.
- The LLM provider receives the selected context. Use synthetic data only; never upload real production logs
  containing personal or confidential information.
- Dependency versions are bounded but not hash-pinned; run `pip-audit` / image scanning in a real pipeline.
