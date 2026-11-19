# RootCause Copilot v1.1 - Architecture

RootCause Copilot is a **modular monolith**: one Python process (Streamlit) with clear internal boundaries. Nothing
about the Day 4 concepts needs microservices, and students can read the whole system. Every name in the diagrams
below is a real module or function in this repository.

## 1. Overall application architecture

```mermaid
flowchart LR
    U["Engineer / student<br/>(browser)"] --> UI["Streamlit UI<br/>app.py + ui/*.py"]
    UI -->|"IncidentInput"| ORCH["core/orchestrator.py<br/>run_investigation()"]
    UI -->|"API key (session only)"| SS[("st.session_state<br/>short-term")]
    ORCH --> AG["core/agent.py<br/>LLMAgent / rule-based routing"]
    AG -->|"Live AI Mode only"| GROQ["Groq API<br/>openai/gpt-oss-20b"]
    ORCH --> TX["core/tool_executor.py<br/>ToolExecutor"]
    TX --> TOOLS["tools/<br/>log_analyzer · error_pattern_analyzer<br/>incident_retriever · document_search<br/>kubernetes_analyzer · report_generator"]
    ORCH --> CTX["core/context_manager.py"]
    ORCH --> REF["core/reflection.py"]
    ORCH --> APR["core/approval.py"]
    ORCH --> TRC["core/trace.py"]
    TOOLS --> DB[("SQLite<br/>memory/*.py")]
    APR --> DB
    ORCH --> DB
```

| Package | Responsibility |
|---|---|
| `app.py`, `ui/` | Navigation, pages, sidebar **AI Configuration**, page-level error boundary |
| `core/` | Workflow (`orchestrator`), agent, tool registry/executor, context, reflection, approval, events, trace, Groq client, safe logging |
| `tools/` | Deterministic tools - they compute facts; they never call the LLM |
| `memory/` | SQLite schema, migrations and repositories |
| `config.py` | Fixed provider/model, paths, limits, labels |

## 2. RootCause Agent workflow (one investigation)

```mermaid
flowchart TD
    A["Incident Received<br/>(simulated alert or form)"] --> B["Log Analysis"]
    B --> C["Error Pattern Analysis"]
    C --> D["Historical Incident Search"]
    D --> E{"Docs indexed?"}
    E -- yes --> F["Knowledge Base Search"]
    E -- no --> G
    F --> G{"YAML attached?"}
    G -- yes --> H["Kubernetes Configuration Analysis"]
    G -- no --> I
    H --> I["Context Extracted<br/>rank · dedupe · budget"]
    I --> J["Root-Cause Hypothesis"]
    J --> K{"Evidence Verification<br/>verdict?"}
    K -- "revise (round 1)" --> J2["Revised hypothesis"] --> K
    K -- "supported / insufficient / round 2 done" --> L{"Production-changing<br/>action?"}
    L -- yes --> M["Human Approval<br/>(Awaiting Approval)"]
    L -- no --> N
    M --> N["Investigation Report Generated<br/>+ SQLite memory write-back"]
```

The order above is the **Demo Mode** (rule-based) order. In **Live AI Mode** the model chooses which tools to call
and in which order; steps it does not need are shown as **Skipped** in the trace. Every step's status, real
timestamp, measured duration and *origin* are recorded by `core/trace.py`:

| Origin label | Meaning |
|---|---|
| `executed (deterministic code)` | Python code really ran (tools, context, checks, report) |
| `executed (Groq LLM call)` | the model produced this result live |
| `executed (rule-based heuristic - no AI)` | Demo Mode heuristic for inputs without a prepared result |
| `SIMULATED DEMO RESULT (predefined - no AI reasoning)` | prepared output for a bundled sample incident |
| `human decision (simulated approval workflow)` | approve / reject / more information |

Statuses: **Pending** (never reached), **Running**, **Completed**, **Failed**, **Skipped** (with the reason),
**Awaiting Approval**. Nothing is invented: a step that did not run has no timestamp and no duration.

## 3. Tool-calling architecture

```mermaid
sequenceDiagram
    participant O as orchestrator
    participant M as Groq model
    participant R as tool_registry
    participant X as ToolExecutor
    O->>M: incident summary + tool definitions (chat_tools)
    M-->>O: tool call: search_error_patterns {query, reason}
    O->>R: validate_tool_call(name, args)
    alt not allowlisted / invalid arguments
        R-->>O: ToolValidationError
        O->>M: tool message {"error": "Invalid tool call ..."}
    else valid
        R-->>O: clean arguments
        O->>X: run(name, args) - bounded retries
        X-->>O: ToolResult (or honest failure)
        O->>M: tool message (result truncated to 2,500 chars)
    end
    M-->>O: no tool call ("READY") or limit reached
    O->>M: diagnose(context) - JSON mode
    O->>M: review(context, diagnosis) - JSON mode
```

- Allowlisted tools: `analyze_logs`, `search_error_patterns`, `retrieve_similar_incidents`, `search_knowledge_base`,
  `analyze_kubernetes_yaml`; `generate_investigation_report` is orchestrator-only.
- Limits (`config.py`): 8 tool calls, 10 model turns, 2 reflection rounds, 9,000-character context budget,
  45 s API timeout, 2 bounded retries for transient errors only.
- `openai/gpt-oss-20b` on Groq supports tool use and JSON mode, but not parallel tool calls; JSON-schema structured
  outputs cannot be combined with tool use. Hence: native tool calling for tool choice, JSON mode + Python
  validation for diagnosis and review. An invalid model tool call (`tool_use_failed`) makes that one step use
  rule-based routing, and the timeline says so.
- There is no shell, file-system, network or infrastructure tool. The model cannot execute anything.

## 4. Incident memory architecture

```mermaid
flowchart LR
    subgraph ST["Short-term (per browser session)"]
      S1["st.session_state<br/>mode · masked API key · selected incident"]
    end
    subgraph INV["Current investigation (one run)"]
      S2["InvestigationState<br/>evidence gathered so far"]
    end
    subgraph LT["Persistent memory (SQLite file)"]
      T1[("incidents")]
      T2[("timeline_events")]
      T3[("audit_log")]
      T4[("investigation_results<br/>incl. trace")]
      T5[("documents · doc_chunks")]
      T6[("reports")]
    end
    S2 -->|"retrieve_similar_incidents"| T1
    S2 -->|"search_knowledge_base"| T5
    S2 -->|"write-back: symptoms, patterns,<br/>hypothesis, evidence, actions"| T1
    CLOSE["Close incident form<br/>(root cause · resolution · lessons)"] --> T1
```

- Retrieval score (`tools/incident_retriever.py`): `0.45 × keyword overlap + 0.35 × log-pattern overlap +
  0.20 × same service`; only incidents with a recorded root cause or resolution are returned.
- Knowledge base: keyword TF-IDF over chunks with a **relevance filter** (`KB_MIN_MATCHED_TERMS = 2`): if nothing
  is relevant, nothing is placed in the model's context.
- `init_db()` creates the schema, **migrates** v1.0 databases in place (new columns `supporting_evidence`,
  `recommended_actions`, `evidence_assessment`) and loads fictional seed history once.
- Database path: `$ROOTCAUSE_DATA_DIR/rootcause.db` (default `./data_store/`, git-ignored; `/data` in Kubernetes).

## 5. Human-in-the-loop approval

```mermaid
stateDiagram-v2
    [*] --> Proposed: remediation from final hypothesis
    Proposed --> NotRequired: read-only action
    Proposed --> AwaitingApproval: production-changing or unknown action
    AwaitingApproval --> Approved: Approve (reviewer)
    AwaitingApproval --> Rejected: Reject (rationale required)
    AwaitingApproval --> AwaitingApproval: Request more information (rationale required)
    Approved --> SimulatedExecution: audit "SIMULATED ONLY - would run ..."
    Rejected --> Investigating: choose alternative / gather evidence
    NotRequired --> [*]
    SimulatedExecution --> [*]
```

Every decision is appended to `audit_log` (investigation ID, action, decision, reviewer, timestamp, rationale,
simulated execution note) and reflected in the saved trace. Risk levels come from `core/schemas.ACTION_RISK`
(unknown action types are **High** and always require approval).

## 6. Day 5 Docker / Kubernetes deployment

```mermaid
flowchart LR
    SRC["Repo rootcause-copilot<br/>(code + kubernetes/)"] -->|"docker build"| IMG["Image<br/>user/rootcause-copilot:latest"]
    IMG -->|"docker push"| HUB[("Docker Hub")]
    subgraph K8S["Kubernetes cluster (Rancher Desktop / k3s)"]
      subgraph NS["namespace: rootcause"]
        SVC["Service rootcause-copilot<br/>port 80 → 8501"] --> POD["Pod (1 replica, Recreate)<br/>non-root · probes on /_stcore/health"]
        CM["ConfigMap rootcause-config"] -.-> POD
        SEC["Secret rootcause-groq<br/>(created with kubectl, optional)"] -.-> POD
        POD --> PVC[("PVC rootcause-data 1Gi<br/>mounted at /data")]
      end
    end
    HUB -->|"pull (imagePullPolicy Always)"| POD
    USER["Browser"] -->|"kubectl port-forward 8501:80"| SVC
```

One replica on purpose: SQLite on a single `ReadWriteOnce` volume is not a shared, multi-writer database.
Production designs would use PostgreSQL or a managed database (deliberately deferred).

## 7. ArgoCD GitOps workflow

```mermaid
sequenceDiagram
    participant Dev as Instructor / student
    participant Git as GitHub repo (kubernetes/ on main)
    participant Argo as ArgoCD (namespace argocd)
    participant K8s as Kubernetes (namespace rootcause)
    Dev->>Git: ROOTCAUSE_APP_VERSION gitops-v1 → gitops-v2, commit, push
    Argo->>Git: poll (~3 min) / Refresh
    Argo->>K8s: automated sync (Recreate rollout)
    K8s-->>Argo: Healthy + Synced
    Dev->>K8s: kubectl delete service (drift)
    Argo->>K8s: self-heal re-creates it
    Dev->>Git: git revert HEAD, push (rollback)
    Argo->>K8s: sync back to gitops-v1
```

One repository: application code and desired state (`kubernetes/`, watched by `argocd/rootcause-copilot-application.yaml`)
live together; Docker Hub holds the built image. Automated sync + self-heal, pruning off; the PVC and Namespace
carry `Prune=false,Delete=false`. No Secret ever lives in the repository.

## 8. Security boundaries

| Boundary | Control |
|---|---|
| Uploads (untrusted) | extension allowlist, 2 MB limit, empty/binary checks, filename sanitising, safe PDF/YAML parsing, `<untrusted_evidence>` wrapping, injection flagging |
| Model output (untrusted) | schema validation, normalisation, unknown action → approval, no execution capability |
| Secrets | key only in session memory or a Kubernetes Secret env var; redacted from logs; masked in UI; Secret values masked in the YAML analyzer |
| Errors | friendly messages in the UI (`showErrorDetails = "none"`), details only in the redacted log file |

See [SECURITY.md](SECURITY.md) for limitations.
