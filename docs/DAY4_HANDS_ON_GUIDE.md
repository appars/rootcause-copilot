# Day 4 Hands-On Guide - RootCause Copilot on your Windows laptop

**Goal:** run RootCause Copilot v1.1 locally on Windows 10/11, investigate a (simulated) production incident and see
the seven Day 4 Agentic AI concepts working. No Docker or Kubernetes is needed today.

Time: about 150 minutes. All commands are for **Windows PowerShell** (not Linux/macOS shells).

---

## Part 0 - What you need

| Item | Required? | Check |
|---|---|---|
| Windows 10 or 11 | yes | - |
| Git for Windows | yes | `git --version` |
| Python 3.12 (3.11-3.13 should work) | yes | `python --version` or `py --version` |
| Internet access | for installing packages and Live AI Mode | - |
| Your own Groq API key | only for Live AI Mode (Demo Mode needs none) | Groq console |

### Install Git (if `git --version` fails)
Download *Git for Windows* from git-scm.com, install with the default options, then **close and reopen PowerShell**.

### Install Python (if neither `python` nor `py` works)
Download Python 3.12 for Windows from python.org. In the first installer screen tick
**"Add python.exe to PATH"**, then *Install Now*. Close and reopen PowerShell.

> **Windows Store trap:** if `python` opens the Microsoft Store or prints nothing, use the launcher `py`
> instead, or disable *Settings → Apps → Advanced app settings → App execution aliases → python.exe*.

### `python` versus `py`
- `python` runs whichever Python is first on your **PATH** (check with `where.exe python`).
- `py` is the **Python Launcher for Windows**; it finds installed versions even when PATH is not set.
  `py -0` lists them, `py -3.12` picks one.
- Use either one to **create** the virtual environment. After activation, `python` always means the venv's Python.

---

## Part 1 - Get the code and set up a virtual environment

Open **PowerShell** (Start menu → type *PowerShell* → open). Choose a working folder, e.g. your Documents:

```powershell
cd $HOME\Documents
git --version
python --version          # if "not recognized", use:  py --version
```

Clone the repository (the instructor shares the real URL; until then it is the placeholder below):

```powershell
git clone <REPOSITORY_URL>
cd rootcause-copilot
dir                        # you should see app.py, requirements.txt, core, tools, ...
```

Create and activate a **virtual environment** - a private folder of Python packages just for this project, so it
cannot clash with other projects:

```powershell
python -m venv .venv               # or:  py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Success looks like this:** the prompt now starts with `(.venv)`, for example
`(.venv) PS C:\Users\you\Documents\rootcause-copilot>`.

### If activation is blocked ("running scripts is disabled on this system")
Allow scripts **for this PowerShell window only** (nothing system-wide changes; it resets when you close the window):

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Alternative without changing any policy: use Command Prompt (`cmd`) and run `.venv\Scripts\activate.bat`.

### Verify you are using the project's Python

```powershell
python -c "import sys; print(sys.executable)"
```
It must end in `rootcause-copilot\.venv\Scripts\python.exe`. If it does not, activate again.

### Install the dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Install problems? See [TROUBLESHOOTING.md](TROUBLESHOOTING.md#dependency-installation) (proxy, very new Python version,
"Microsoft Visual C++ required", disk space).

---

## Part 2 - Start the app

```powershell
python -m streamlit run app.py
```

Your browser opens **http://localhost:8501**. If not, open that address yourself.
The first start may ask for an e-mail address in the terminal - just press **Enter**.

- **Stop the app:** click in the PowerShell window and press **Ctrl+C**.
- **Port 8501 busy?** `python -m streamlit run app.py --server.port 8502` and open http://localhost:8502.
- **Leave the virtual environment** (when you are done for the day): `deactivate`.

You start in **Demo Mode** (orange banner). Everything works without a key.

---

## Part 3 - Configure Live AI (Groq) - or use Demo Mode

The app starts in **Demo Mode** (orange banner) so you can begin immediately. **Live AI Mode** is the primary mode:

1. Get **your own** key from the Groq console (usage is subject to your account limits, rate limits and pricing).
2. In the app's **sidebar → AI Configuration**: paste the key into the password field → **🔌 Connect / Test connection**.
3. The app makes a **real** request to Groq. You will see one of:

| Status | Meaning | What to do |
|---|---|---|
| 🟢 Connected - model available | key accepted, `openai/gpt-oss-20b` reachable; **Live AI Mode** is now selected | continue |
| 🔴 Key rejected by Groq | wrong / revoked / truncated key | re-paste (no spaces) |
| 🔴 Model not accessible | your account cannot use the fixed model | tell the instructor |
| 🟠 Could not verify | network, timeout, rate limit or Groq service error | retry later, or use Demo Mode |

4. The key is shown only as `••••••••` + last 4 characters. **🗑️ Clear API key** removes it.

Rules: never type the key into a PowerShell command, a project file, a chat or a screenshot. The app keeps it only
in your browser session on the server. No key or no internet? Stay in **Demo Mode** - every exercise still works,
and predefined AI results are labelled **SIMULATED DEMO RESULTS**.

---

## Part 4 - Hands-on lab: investigate the 10:30 AM payment incident

Fill in your worksheet ([DAY4_STUDENT_WORKSHEET.md](DAY4_STUDENT_WORKSHEET.md)) as you go.

1. **Knowledge Base** → **Load bundled sample documents** (six documents become *indexed*).
2. **New Investigation** → tab **📦 Sample incident library** → open **INC-001** and read its description.
3. Tab **🚨 Simulated alert** → keep *PaymentServiceHighErrorRate* → **🚨 Simulate New Incident Alert**.
   Watch the status box: steps turn 🔄 Running → ✅ Completed live.
4. Work through the result tabs:

| Tab | What to look at | Concept |
|---|---|---|
| **Execution trace** | every step with status, start time, measured duration and **origin** (*executed* vs **SIMULATED DEMO RESULT**); skipped steps show *why* | agent · tools · decisions |
| Evidence | counts, chronological sequence, stack traces, suspicious lines - all computed by code | facts vs. hypotheses |
| Context & memory | characters used vs. budget, excluded items; **three kinds of memory** side by side | context · memory |
| Agent actions | which tool, chosen by whom (rules / AI), and why | dynamic decisions |
| Similar incidents | the green **🧠 Memory** banner: which past incident was retrieved, its ID and match reasons | persistent memory |
| Diagnosis & evidence | initial vs. final hypothesis; evidence label (*Strong / Partial / Contradictory / Insufficient*); contradictory evidence; missing information | reflection |
| Approval | proposed action, reason, evidence, impact, **risk level**, side effects | human approval |
| Close & report | save root cause / resolution / lessons; download Markdown/PDF | memory · reporting |
| Event log | detailed events, incl. retries and simulated events | auditability |

5. **Upload logs yourself:** tab **✍️ Manual** → title, *Affected service* = `order-service`, severity SEV2,
   description, upload `data\sample_logs\inc002_order_service.log`, optional context
   ("Started after 14:00, no deployment today") → **▶ Run investigation**.
6. **Approval:** type your name. Click **Reject** without a rationale - what happens? Add a rationale and
   **Request more information**. Finally **Approve (simulated)** and read the *Execution* column - nothing real ran.
7. **Report:** **Close & report** → write the root cause in your own words, add a lesson learned →
   **Close incident and save to memory** → **Download PDF**.

### Error recovery (Concept 6)
8. Open **🧪 Instructor controls** (bottom of the start section) → *knowledge base times out once* → run the
   sample incident INC-002. Find the 🔁 *retrying* and ♻️ *recovered* rows in the timeline.
9. Switch to *knowledge base unavailable* and run again. The investigation still completes, the knowledge base
   evidence is missing, and the limitation is listed honestly. Switch back to *No simulated failure*.
10. Upload `data\error_samples\empty.log` and `too_large.log` in the **Manual** tab, and
   `corrupt_report.pdf` in the Knowledge Base. Each is rejected with a clear message - never "indexed".

### Kubernetes analyzer
11. **Kubernetes Analyzer** → load `common_mistakes.yaml` → **Analyze**. For each finding read *Evidence* and
    *Recommended correction*. Find the selector mismatch, the `latest` tag and the masked Secret value. Then load
    `inc004_notification_service.yaml` - which ConfigMap **and** which Secret reference are missing?

### Persistence - the key demo
12. In PowerShell press **Ctrl+C**, then start again: `python -m streamlit run app.py`.
13. Open **Incident History**: your closed incident is still there. Your API key, however, is gone
    (session state was cleared). That is the difference between **session state** and **persistent memory**.
14. Run sample incident **INC-001** again. The **🧠 Memory** banner now lists your own closed incident.
    Memory written by one investigation helps the next one.

Where is the data? `rootcause-copilot\data_store\rootcause.db` (git-ignored). Deleting that file resets memory.

---

## Part 5 - Read the code

Open the project in VS Code (`code .`) or any editor.

| Read this | To understand |
|---|---|
| `core/orchestrator.py` | the whole workflow, step by step |
| `core/trace.py` | how the execution trace records status, timing and origin honestly |
| `core/agent.py` → `rule_based_next_step` | how the next tool is chosen without an LLM |
| `core/tool_registry.py` | the tool allowlist and argument validation |
| `core/context_manager.py` | ranking, de-duplication and the context budget |
| `core/reflection.py` | the reviewer checks |
| `core/approval.py` | why every production change needs approval |
| `tools/incident_retriever.py` | the similarity score |

---

## Part 6 - Mini challenge (30 minutes)

**Challenge: Investigate an unfamiliar incident and justify your root-cause hypothesis using evidence from logs and
historical incidents.**

1. New Investigation → **📦 Sample incident library** → **CHALLENGE-01 - Search service** (marked
   *challenge - no predefined demo result*) → run it. Use **Live AI Mode** if you can; in Demo Mode only a
   rule-based heuristic runs, so **you** must do the reasoning.
2. Use the Evidence tab (chronological sequence!), Similar incidents, Kubernetes findings and the knowledge base.
3. Decide: what changed, what is the mechanism, what is ruled out (and by which lines), what you would do first.

**Submit** (see [HOMEWORK_SUBMISSION.md](HOMEWORK_SUBMISSION.md#part-a---day-4-mini-challenge)):
1. a screenshot of your investigation (execution trace visible),
2. your root-cause hypothesis (3-5 sentences),
3. the evidence supporting it - cite log line numbers (`L..`) and historical incident IDs,
4. your recommended corrective action and its risk / approval need,
5. the downloaded investigation report (PDF or Markdown).

### Optional code extensions (if you finish early)
1. **New log pattern** - add a `disk_pressure` pattern (`No space left on device`, `disk usage 9x%`) in
   `tools/error_pattern_analyzer.py`; add a test in `tests/test_log_analyzer.py`.
2. **Better memory** - change the weights in `score_incident` (`tools/incident_retriever.py`). Does `HIST-2026-031`
   still rank first for INC-001? Why is the distractor `HIST-2025-090` lower?
3. **New reviewer check** - in `core/reflection.py`, flag *high* confidence when no similar incident was found.
4. **Safer approvals** - make *Approve* require a reviewer name (raise `ValueError` in `record_decision`).

Run the tests after any change:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest
```

---

## Part 7 - Troubleshooting quick table

| Symptom | Fix |
|---|---|
| `python` not recognized | use `py`, or reinstall Python with *Add to PATH*, reopen PowerShell |
| `Activate.ps1 cannot be loaded` | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` |
| `ModuleNotFoundError: streamlit` | venv not active: `.\.venv\Scripts\Activate.ps1`, then install again |
| Port in use | `--server.port 8502` |
| 🔴 Key rejected | re-paste the key in the sidebar; no spaces; or use Demo Mode |
| 🟠 Could not verify / rate limit (429) | wait a minute; check internet and your Groq limits; or Demo Mode |
| Data seems "stuck" | stop the app, delete `data_store\rootcause.db`, start again |

More: [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Interview questions (practise aloud)

1. What is the difference between session state and persistent memory? Show it in this app.
2. Why does the agent not send all logs to the LLM?
3. How does the agent decide which tool to call next, and what stops it from looping forever?
4. What starts an investigation in an event-driven system? What decides the next step after that?
5. Does self-reflection guarantee a correct diagnosis? Why not?
6. When should a failing call be retried, and when not? Give one example of each.
7. Why must a production restart require human approval - and why is a UI button not enough in a real company?
8. Which numbers in the report come from code, and which come from a model? Why does that matter?
