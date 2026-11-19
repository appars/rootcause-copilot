# Troubleshooting

Windows commands are PowerShell unless stated otherwise.

## Python and PATH

| Symptom | Fix |
|---|---|
| `python : The term 'python' is not recognized` | Try `py --version`. If that works, use `py -3.12 -m venv .venv` and, after activation, `python` works inside the venv. Otherwise reinstall Python from python.org with **Add python.exe to PATH**, then open a **new** PowerShell. |
| `python` opens the Microsoft Store | Settings → Apps → Advanced app settings → App execution aliases → turn off *python.exe* / *python3.exe*. |
| Several Python versions | `py -0` lists them; create the venv with the one you want: `py -3.12 -m venv .venv`. |
| Very new Python (e.g. 3.14) and install fails | Some dependencies may not publish wheels yet. Install Python 3.12 and recreate the venv. |

## Virtual environment activation

| Symptom | Fix |
|---|---|
| `Activate.ps1 cannot be loaded because running scripts is disabled` | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` - affects **only this window**, nothing system-wide. Or use `cmd` and `.venv\Scripts\activate.bat`. |
| No `(.venv)` in the prompt | You are not in the venv - run `.\.venv\Scripts\Activate.ps1` from the project folder. |
| Wrong interpreter | `python -c "import sys; print(sys.executable)"` must end in `.venv\Scripts\python.exe`. |
| Folder moved/renamed and venv broken | Delete `.venv` (`Remove-Item -Recurse -Force .venv`) and create it again. |

## PowerShell execution policy

The session-scoped command above is enough for the workshop. Do **not** change the machine-wide policy
(`-Scope LocalMachine`) unless your IT policy allows it and you understand the impact.

## Dependency installation

| Symptom | Fix |
|---|---|
| `pip` is old / resolver errors | `python -m pip install --upgrade pip` then retry. |
| `ModuleNotFoundError: No module named 'streamlit'` | venv not active, or installed into another Python - activate and reinstall. |
| SSL / proxy errors | College proxy: `python -m pip install --proxy http://<proxy>:<port> -r requirements.txt` (ask the lab admin). |
| "Microsoft Visual C++ 14.0 required" | A wheel is missing for your Python version - use Python 3.12 (wheels exist for all dependencies). |
| Disk full | Free space; the venv needs roughly 0.5-1 GB. |

## Streamlit startup and port

| Symptom | Fix |
|---|---|
| Asks for an e-mail on first run | Press Enter (optional). |
| `Port 8501 is already in use` | `python -m streamlit run app.py --server.port 8502`, or find the process: `Get-NetTCPConnection -LocalPort 8501 \| Select-Object OwningProcess` then `Stop-Process -Id <pid>`. |
| Browser does not open | Open http://localhost:8501 manually. |
| Firewall prompt | Allow on *private* networks only (or cancel - localhost still works). |
| Stop the app | Ctrl+C in the PowerShell window. |

## Groq authentication, rate limits and timeouts

Sidebar **AI Configuration → Connect / Test connection** makes a real request. Status and fix:

| Status / message | Meaning / fix |
|---|---|
| ⚪ Not configured | No key yet. Paste one, or keep using Demo Mode. |
| 🟡 Key available - not tested yet | e.g. a server-side key; click Connect to verify it. |
| 🔴 Key rejected by Groq | Wrong, revoked or truncated key. Re-paste (no spaces). Not retried; the key is not stored. |
| 🔴 Model not accessible | The fixed model `openai/gpt-oss-20b` is not available to this account/region - tell the instructor. |
| 🟠 Could not verify | Network/firewall, timeout, HTTP 429 rate limit or a Groq service error. Retried twice with backoff, then stopped. Check internet and your account limits, retry later, or use Demo Mode. |
| During an investigation: **Invalid output** | The model did not return valid JSON twice; run the investigation again. |
| Live AI Mode cannot be selected | No key in this session - connect it in the sidebar. |
| Investigation "stopped" | Live AI became unavailable mid-run; evidence collected so far is saved. Use **Continue in Demo Mode** or retry. |

The app never switches from Live to Demo Mode on its own - it offers it. **Settings → Run capability check** tests
connection, tool calling and JSON mode.

## Unexpected errors and the technical log

Students see a short friendly message, never a stack trace. Details go to `data_store\logs\app.log`
(or `$ROOTCAUSE_DATA_DIR\logs\app.log`); API keys are redacted. Send that file to the instructor if a page keeps
failing. One failed investigation is marked *failed* in its trace; other investigations are unaffected.

## File upload and PDF extraction

| Message | Meaning |
|---|---|
| "is empty" / "contains no readable text" | Upload a file with content. |
| "Unsupported file type" | Logs: `.log`, `.txt`. Documents: `.txt`, `.md`, `.log`, `.pdf`. YAML: `.yaml`, `.yml`. |
| "is X MB; the limit is 2.0 MB" | Upload only the incident window (e.g. 10 minutes of logs). |
| "looks like a binary file" | You uploaded e.g. a .zip renamed to .log. |
| "could not be read as a PDF" | Corrupt PDF - it is recorded as **failed**, not indexed. |
| "No text could be extracted ... image-only PDF" | Scanned PDF; OCR is not supported. |

## YAML parsing

"Invalid YAML (line N, column M)" - usually indentation (spaces only, no tabs) or a missing `:`. The analyser uses
`yaml.safe_load_all`, so Python-specific tags are rejected by design.

## SQLite persistence and permissions

| Symptom | Fix |
|---|---|
| "Database problem ... Check that the data folder is writable" | The folder `data_store\` (or `$ROOTCAUSE_DATA_DIR`) must be writable. Avoid running from a read-only or cloud-synced folder that locks files (e.g. some OneDrive setups) - use `Documents\` outside OneDrive or set `$env:ROOTCAUSE_DATA_DIR = "C:\temp\rootcause"`. |
| `database is locked` | Two app instances using the same file - stop one. |
| Reset memory | Stop the app, delete `data_store\rootcause.db`, start again (seed history reloads). |
| In Kubernetes: data lost after redeploy | Check the PVC is `Bound` and mounted at `/data`; `ROOTCAUSE_DATA_DIR=/data` in the ConfigMap. |

## Docker build and registry

| Symptom | Fix |
|---|---|
| `Cannot connect to the Docker daemon` / `error during connect` | Rancher/Docker Desktop not running; engine is containerd (use `nerdctl` or switch to dockerd); wrong `docker context` |
| `denied: requested access to the resource is denied` on push | `docker login -u <you>` with an access token; the image name must start with **your** Docker Hub user |
| `invalid reference format` | uppercase letters or spaces in the image name |
| Build very slow | first build downloads the base image; later builds reuse cached layers |
| Container `unhealthy` | `docker logs rootcause`; allow 30-60 s for the first start |
| `port is already allocated` | another app/container uses 8501 → `-p 8502:8501` |
| Data gone after re-creating the container | `-v rootcause-data:/data` was missing |
| `exec format error` | image built for another CPU (arm64 vs amd64) → multi-platform build (README_MAC.md, E4) |

## Rancher Desktop runtime

- dockerd (moby) → `docker` CLI (used in the guides); containerd → `nerdctl` CLI.
- Switching engines restarts the VM; images built in one engine are not visible in the other.
- Windows needs WSL 2 and hardware virtualization; *Troubleshooting → Reset Kubernetes* if it hangs.
- Give the VM ≥ 4 GB memory (6 GB with ArgoCD).

## Kubernetes context, PVC, probes and image pull

| Symptom | Fix |
|---|---|
| Deploying to the wrong cluster | `kubectl config current-context` → `kubectl config use-context rancher-desktop` (Docker Desktop: `docker-desktop`) |
| `InvalidImageName` | the literal `DOCKERHUB_USERNAME` placeholder (uppercase) is still in `kubernetes/deployment.yaml` |
| `ErrImagePull` / `ImagePullBackOff` | image not pushed, name typo, or repository private. `kubectl -n rootcause describe pod -l app=rootcause-copilot` |
| New `latest` pushed but old app still runs | `kubectl -n rootcause rollout restart deployment/rootcause-copilot` (`imagePullPolicy: Always` pulls again) |
| PVC `Pending` | `local-path` binds when the pod is scheduled - wait; `kubectl get storageclass` must show a default |
| Pod restarts / readiness fails | `kubectl -n rootcause logs deploy/rootcause-copilot [--previous]`; first start takes ~20-40 s (startupProbe allows 150 s) |
| `OOMKilled` | increase `limits.memory` in Git (and sync) |
| Port-forward stops after a rollout | the pod was replaced (`Recreate`) - start the port-forward again |
| Secret created but key not used | pods read env vars at start → `kubectl -n rootcause rollout restart deployment/rootcause-copilot` |

## ArgoCD sync and Git repository access

| Symptom | Fix |
|---|---|
| Cannot open https://localhost:8080 | port-forward window closed - `kubectl -n argocd port-forward svc/argocd-server 8080:443`; accept the self-signed certificate |
| `ComparisonError` / repository not accessible | repository private or URL typo; `repoURL` should end in `.git`; `targetRevision: main`; `path: kubernetes` |
| Stays OutOfSync after a push | click **Refresh** (polling is ~3 min); check the commit is on `main`; open the *Diff* |
| `Degraded` | usually the pod: `ImagePullBackOff` (placeholder / not pushed) or `CrashLoopBackOff` (logs) |
| Manual `kubectl` change disappears | expected: self-heal - change Git instead |
| Resource deleted from Git still in the cluster | expected: `prune: false`; delete it by hand or enable pruning deliberately |
| Rollback button disabled | auto-sync is on - roll back with `git revert` |
| `Unknown` health / CRD errors | ArgoCD install incomplete - re-run the install with `--server-side --force-conflicts` |
| Lost admin password | `kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}"` and decode (see the platform READMEs) |
