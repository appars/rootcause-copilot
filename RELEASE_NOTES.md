# Release Notes - RootCause Copilot

## v1.1 - Workshop release (Day 4 + Day 5)

**RootCause Copilot – AI-Powered IT Operations Investigation Platform.** This release builds on v1.0. It keeps the
investigation engine, the tool registry and the database, and it makes the agent's work **visible**, the evidence
**honest**, and the deployment **safer**.

### Highlights

| Area | v1.0 | v1.1 |
|---|---|---|
| Groq key entry | Settings page | **Sidebar → AI Configuration**: masked key, real *Connect / Test*, *Clear*, live status, fixed model name |
| Mode labelling | "Demo Mode" | **SIMULATED DEMO RESULTS** banner, plus a per-step origin label in the trace |
| Agent visibility | Event log | **Execution trace** with Pending / Running / Completed / Failed / Skipped / Awaiting Approval, measured durations, origin, and the reason a step was skipped |
| Evidence quality | Confidence high / medium / low | Plus an **evidence label** (Strong / Partial supporting / Contradictory / Insufficient evidence) for each reflection round, listing supporting, contradictory and missing evidence. No invented percentages. |
| Log analysis | Pattern counts | New **Error Pattern Analyzer**: stack traces, chronological event sequence, change events (deploy / config / feature flag), suspicious entries |
| Kubernetes analysis | Static checks, finding text only | **27 check types**, each finding with evidence and a recommended correction; 5 new: invalid replicas, probe port mismatch, limits below requests, RWO volume with more than one replica, unused volume |
| Incident intake | Library + manual | **🚨 Simulate New Incident Alert**, a service dropdown, free-text context notes, and sanitised upload names |
| Approval | Approve / reject | Each action shows its **risk level**, reason and side effects. The decision updates the trace. |
| Report | 9 sections | **15 sections**, including the trace table, evidence assessment, risk and the demo label |
| Day 4 challenge | - | **CHALLENGE-01** (search service, feature-flag → CPU throttling), with *no* predefined demo answer |

### New features

- `core/trace.py`: an execution trace that is recorded live (`st.status`) and stored with each investigation.
- `tools/error_pattern_analyzer.py`: the deterministic catalogue of error patterns, used by the log analyzer and the agent tool.
- `core/logging_setup.py`: a rotating technical log at `data_store/logs/app.log`. Groq keys and `Authorization`/`api_key` values are redacted.
- `reflection.assess_evidence()`: evidence labels with their reasons.
- `schemas.ACTION_RISK`: a Low / Medium / High risk for each allow-listed action. Unknown actions default to High.
- History stores and shows `supporting_evidence`, `recommended_actions` and `evidence_assessment`.
- Dashboard: Open/Resolved counts, investigations vs. seeded history, and charts by severity and by service.
- `kubernetes/groq-secret.template`: a Secret template containing only a placeholder. The real file name `*.secret.yaml` is git-ignored.

### Bug fixes

- False positives: a healthy connection-pool status line (`waiting=0`) and the word `payment_events` were flagged as errors. Both regexes are now tightened.
- The rule-based router used to focus on generic symptoms (for example `slow_transaction`). It now picks the most frequent **specific** pattern.
- The knowledge-base search returned unrelated runbooks for single-word matches. Matches now need at least 2 terms, and "runbook" is a stopword.
- The mode radio button could fall out of sync with the session after connecting. It now uses a keyed widget with a callback.
- The hypothesis step's duration included the reflection time. Steps are now timed separately, and *Awaiting Approval* shows no fake duration.
- Unexpected exceptions showed Streamlit stack traces to students. Students now see a friendly message (`showErrorDetails = "none"`), and the details go to the log.
- Filenames from uploads are sanitised (path separators, control characters, length).

### Architecture changes

- Root-level `ARCHITECTURE.md` with 7 Mermaid diagrams (application architecture, agent workflow, tool calling, incident memory, human-in-the-loop approval, Docker/Kubernetes deployment, ArgoCD GitOps) plus security boundaries and `SECURITY.md`.
- In-place SQLite migration (`MIGRATIONS` + `ALTER TABLE ADD COLUMN`). A v1.0 database upgrades without data loss.
- `InvestigationState` carries `kb_documents` and `context_notes`. Context notes are wrapped as `<untrusted_evidence>` and checked for prompt-injection text.
- **Instructor material separated:** `INSTRUCTOR_ANSWER_KEY.md`, `INSTRUCTOR_NOTES.md` and `DEMO_SCRIPT.md` moved out of the student app repository into the `instructor/` folder of the workshop bundle.

### Deployment changes

- `deployment.yaml` hardening: `seccompProfile: RuntimeDefault`, `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`, `automountServiceAccountToken: false`. The pod still runs as non-root UID 10001 with probes and limits.
- `pvc.yaml`: `argocd.argoproj.io/sync-options: Prune=false`, so an accidental deletion from Git cannot wipe incident memory.
- Dockerfile: `HOME=/tmp` for a non-root user without a home directory.
- Day 5 guides: install steps for Rancher Desktop and Docker Desktop, kubectl via `winget`, creating a Docker Hub repository and verifying push/pull, a direct `kubectl apply -k` path, connecting a GitOps repository in ArgoCD, a pruning caution, mandatory vs. optional steps, and a low-resource fallback.

### Known limitations

- **Demo Mode is predefined.** For INC-001 … INC-004 the stored demo output necessarily contains the expected diagnosis. It shows the workflow, not reasoning. CHALLENGE-01 has **no** demo answer: Demo Mode falls back to a rule-based, partial result.
- The fixed model `openai/gpt-oss-20b` cannot combine tool calling with JSON-schema structured outputs. The app uses tool calling and JSON mode in separate steps.
- SQLite plus a `ReadWriteOnce` volume means **one replica only**. This is not a highly available design.
- A server-side key (Kubernetes Secret) is shared by everyone who can open the app. Use it only on a trusted classroom cluster.
- **Not executed in the build environment:** live Groq API calls, the Docker build, Windows runs, a Kubernetes cluster, and ArgoCD sync. See [docs/TEST_RESULTS.md](docs/TEST_RESULTS.md) for what was and was not verified.

## v1.0 - Initial workshop release

Agentic investigation workflow (Groq tool calling), SQLite incident memory, context manager, reflection, human
approval with audit, four sample incidents, Markdown/PDF reports, Docker/Kubernetes/ArgoCD manifests, Day 4/Day 5 guides.
