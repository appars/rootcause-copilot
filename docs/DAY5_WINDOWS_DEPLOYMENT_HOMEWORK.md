# Day 5 Homework (Windows 10/11) - Containerise and deploy RootCause Copilot v1.1 with GitOps

You watched the instructor do this on a Mac. Now try it on **your Windows laptop** with a container runtime
(**Docker Desktop** or **Rancher Desktop**), **Kubernetes** and **ArgoCD**. All commands are **PowerShell**. Mac commands from the demo do not
always work on Windows (for example `sed -i ''`, `read -s`, `base64 -d`) - use the versions below.

Not every laptop can run local Kubernetes. That is fine: there is a **fallback path** and **partial credit**
(Section 10). Submit with [HOMEWORK_SUBMISSION.md](HOMEWORK_SUBMISSION.md).

> 🔐 Never commit or screenshot: API keys, Docker Hub passwords/tokens, the ArgoCD admin password, kubeconfig files
> or Secret YAML. Base64 is not encryption.

## 0. Containers vs. Kubernetes - and what is mandatory

- A **Docker container** packages *one* application with its dependencies and runs it on *one* machine
  (`docker run`). If it crashes, nothing restarts it unless you do.
- **Kubernetes** *orchestrates* containers: it keeps the desired number running, restarts failed ones, attaches
  storage (PVC), gives them a stable network name (Service) and rolls out new versions.
- **ArgoCD** keeps Kubernetes in line with the YAML in a **Git** repository (GitOps).

| Step | Section | Status |
|---|---|---|
| Install a container runtime (Docker Desktop **or** Rancher Desktop) | 2 | **Mandatory** (or use a lab PC) |
| Build and run the image locally | 3 | **Mandatory** |
| Push to Docker Hub and verify the pull | 4 | **Mandatory** |
| Create your GitOps repository with edited manifests | 5 | **Mandatory** |
| Local Kubernetes + namespace + Secret | 2, 6 | Mandatory **if your laptop can run it**, otherwise fallback (§10) |
| ArgoCD install, deploy, OutOfSync → Synced | 7-9 | Mandatory if Kubernetes runs; otherwise explain it (§10) |
| Auto-sync, self-heal, rollback with `git revert` | 9 | **Optional extension** |
| Multi-arch build, `kind`/`minikube` instead of a desktop cluster | - | **Optional extension** |

---

## 1. Hardware and OS guidance (guidance, not a guarantee)

| | Minimum (may be slow) | Recommended |
|---|---|---|
| RAM | 8 GB (give Rancher Desktop 4 GB) | 16 GB (give 6-8 GB) |
| CPU | 4 logical cores | 8 logical cores |
| Free disk | 20 GB | 40 GB |
| Windows | 10 (21H2+) / 11 with **WSL 2** | Windows 11 |
| BIOS/UEFI | **Virtualization (VT-x / AMD-V) enabled** | |

Check virtualization: Task Manager → Performance → CPU → "Virtualization: Enabled".
Check WSL: `wsl --status` (install with `wsl --install` in an **Administrator** PowerShell, then reboot).
Corporate/college-managed laptops may block WSL or virtualization - use the fallback path.

## 2. Install a container runtime and Kubernetes

Choose **one**:

| Option | Container CLI | Kubernetes | Notes |
|---|---|---|---|
| **A. Docker Desktop** | `docker` | built in: *Settings → Kubernetes → Enable Kubernetes* | Free for personal use, education and small businesses (<250 employees and <$10M revenue) per Docker's licence page at the time of writing - verify. Uses WSL 2. Context name `docker-desktop`. |
| **B. Rancher Desktop** (used in the demo) | `docker` (dockerd) or `nerdctl` (containerd) | built in (k3s) | Open source. Context name `rancher-desktop`. Steps below. |
| C. Advanced: `kind` or `minikube` with Docker Desktop | `docker` | separate tool | Optional extension only. |

**Install kubectl** - Docker Desktop and Rancher Desktop both include `kubectl`. If yours is missing:

```powershell
winget install -e --id Kubernetes.kubectl
kubectl version --client
```

**Option A quick check (Docker Desktop):** recent versions: Dashboard → **Kubernetes** view → *Create cluster*
(choose **kubeadm**, single node); older versions: *Settings → Kubernetes → Enable Kubernetes → Apply & Restart*.
Wait for "Kubernetes running", then `kubectl config use-context docker-desktop` and `kubectl get nodes`.
Check `kubectl get storageclass` shows a `(default)` class (kubeadm mode provides `hostpath`) - the PVC needs one.
Data on it survives pod restarts but not a Kubernetes reset.
Everywhere below, read `rancher-desktop` as `docker-desktop`.

### Option B - Rancher Desktop

1. Download Rancher Desktop for Windows from rancherdesktop.io and install it.
2. First start: **enable Kubernetes**, choose the container engine:
   - **dockerd (moby)** - recommended for this homework; you use the `docker` command.
   - **containerd** - you use `nerdctl` instead of `docker` (same flags). There is **no Docker daemon** in this mode.
3. Preferences → Virtual Machine/WSL: give it the memory from the table above. Wait until the status bar says
   Kubernetes is running (first start downloads several hundred MB).

Open a **new** PowerShell window (so PATH includes Rancher's tools) and check:

```powershell
rdctl version
kubectl version --client
kubectl config get-contexts
kubectl config use-context rancher-desktop
kubectl config current-context          # must print: rancher-desktop
kubectl get nodes                       # STATUS Ready
kubectl get storageclass                # expect: local-path (default)
docker version                          # dockerd mode: both Client AND Server sections
# containerd mode instead:  nerdctl version
```

**dockerd vs containerd in one sentence:** both run containers; dockerd gives you the familiar `docker` CLI,
containerd is what Kubernetes itself uses and is driven with `nerdctl`. If `docker version` shows no *Server*,
you are in containerd mode - use `nerdctl` or switch engines (the VM restarts).

## 3. Build and test the image locally

Use your Day 4 clone (`cd $HOME\Documents\rootcause-copilot`). Set your Docker Hub name (lowercase) for this window:

```powershell
$DockerUser = "<DOCKERHUB_USERNAME>"          # e.g. "asha2026" - lowercase only
$Img = "docker.io/$DockerUser/rootcause-copilot"

docker build --build-arg APP_VERSION=day4-v1 -t "${Img}:day4-v1" .
docker image ls $Img
docker run --rm -d --name rootcause -p 8501:8501 -v rootcause-data:/data "${Img}:day4-v1"
docker ps
(Invoke-WebRequest http://localhost:8501/_stcore/health -UseBasicParsing).Content     # expected: ok
Start-Process http://localhost:8501
```

📸 Screenshot: the app running from the container (sidebar shows *Release v1.1 · build day4-v1*).
Create and close one incident, then prove the volume keeps it:

```powershell
docker rm -f rootcause
docker run --rm -d --name rootcause -p 8501:8501 -v rootcause-data:/data "${Img}:day4-v1"
# Incident History still shows your incident
docker rm -f rootcause
```

containerd users: replace `docker` with `nerdctl` in every command above.

## 4. Push to Docker Hub

First create the repository: hub.docker.com → **Repositories → Create repository** → name `rootcause-copilot`,
visibility **Public**. Create an **access token** (*Account settings → Personal access tokens*) and use it instead of
your password.

```powershell
docker login                 # enter your Docker Hub user and the access token - never in a screenshot
docker push "${Img}:day4-v1"
# verify the registry copy: remove the local image and pull it back
docker image rm "${Img}:day4-v1"
docker pull "${Img}:day4-v1"
docker build --build-arg APP_VERSION=day5-v2 -t "${Img}:day5-v2" .
docker push "${Img}:day5-v2"
```

Make the Docker Hub repository **public** (so Kubernetes can pull without credentials). Your laptop's
architecture is almost certainly `amd64`, which matches your local cluster.

## 5. Create your GitOps repository

1. On GitHub create an **empty, public** repository named `rootcause-copilot-gitops`.
2. Copy the starter folder delivered with the workshop (`rootcause-copilot-gitops`) to your Documents folder.
3. Replace the placeholders with PowerShell (no `sed` on Windows):

```powershell
cd $HOME\Documents\rootcause-copilot-gitops
$GhUser = "<GITHUB_USERNAME>"
foreach ($f in "apps\rootcause-copilot\kustomization.yaml", "apps\rootcause-copilot\deployment.yaml") {
  (Get-Content $f) -replace "DOCKERHUB_USERNAME", $DockerUser | Set-Content $f
}
(Get-Content argocd\rootcause-copilot-application.yaml) -replace "GITHUB_USERNAME", $GhUser |
  Set-Content argocd\rootcause-copilot-application.yaml
Select-String -Path apps\rootcause-copilot\kustomization.yaml -Pattern "newName|newTag"
Select-String -Path argocd\rootcause-copilot-application.yaml -Pattern "repoURL"

git init -b main
git add .
git commit -m "RootCause Copilot desired state day4-v1"
git remote add origin "https://github.com/$GhUser/rootcause-copilot-gitops.git"
git push -u origin main
```

Optional sanity check (Kustomize is built into kubectl): `kubectl kustomize apps\rootcause-copilot`

## 6. Namespace and (optional) Secret - without committing anything

```powershell
kubectl create namespace rootcause
$secure = Read-Host "Groq API key (optional - press Enter to skip)" -AsSecureString
$plain  = [System.Net.NetworkCredential]::new("", $secure).Password
if ($plain) { kubectl -n rootcause create secret generic rootcause-groq --from-literal=GROQ_API_KEY=$plain }
Remove-Variable plain, secure
kubectl -n rootcause get secret        # shows names only
```

The Deployment marks this Secret as **optional**, so skipping it is fine - you can paste your key in the app's
sidebar instead. (A file-based template exists at `kubernetes\groq-secret.template`; if you use it, copy it to
`groq.secret.yaml` - that name is git-ignored - and delete the copy after `kubectl apply`.)

## 7. Install ArgoCD

```powershell
kubectl create namespace argocd
kubectl apply -n argocd --server-side --force-conflicts -f https://raw.githubusercontent.com/argoproj/argo-cd/v3.6.1/manifests/install.yaml
kubectl -n argocd rollout status deploy/argocd-server --timeout=300s
kubectl -n argocd get pods
```

Open the UI - keep this window running and use a second PowerShell window for the next steps:

```powershell
kubectl port-forward svc/argocd-server -n argocd 8080:443
```

Browse to **https://localhost:8080** and accept the self-signed certificate warning. Admin password
(PowerShell has no `base64 -d`; do **not** screenshot it):

```powershell
$enc = kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}"
[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($enc))
```

Log in as `admin`.

## 8. Deploy with ArgoCD

```powershell
cd $HOME\Documents\rootcause-copilot-gitops
kubectl apply -f argocd\rootcause-copilot-application.yaml
kubectl -n argocd get applications          # OutOfSync / Missing at first
```

In the UI: **rootcause-copilot → SYNC → SYNCHRONIZE** (manual first sync). Then verify:

```powershell
kubectl -n rootcause get deploy,pods,svc,pvc
kubectl -n rootcause rollout status deploy/rootcause-copilot
kubectl -n rootcause port-forward svc/rootcause-copilot 8501:80       # another window
```

Open http://localhost:8501. 📸 Screenshots: ArgoCD *Synced / Healthy*; `kubectl get pods,pvc` output; the app.

**Persistence:** create and close an incident, then
`kubectl -n rootcause delete pod -l app=rootcause-copilot`; when the new pod is Running, check Incident History.

## 9. GitOps change: OutOfSync → Synced

```powershell
cd $HOME\Documents\rootcause-copilot-gitops
(Get-Content apps\rootcause-copilot\kustomization.yaml) -replace "newTag: day4-v1", "newTag: day5-v2" |
  Set-Content apps\rootcause-copilot\kustomization.yaml
git diff
git commit -am "Release day5-v2"
git push
```

In ArgoCD click **Refresh** → 📸 **OutOfSync** (diff = image tag). Click **Sync** → watch the rollout:
`kubectl -n rootcause get pods -w` (Ctrl+C to stop watching). The sidebar shows *build day5-v2*. 📸 **Synced**.

Optional: enable Auto-Sync and roll back via Git:

```powershell
kubectl -n argocd patch application rootcause-copilot --type merge --patch-file argocd\autosync-patch.json
git revert --no-edit HEAD
git push
```

## 10. Fallback path and partial credit

If your laptop cannot run Rancher Desktop/Kubernetes (no virtualization, managed laptop, < 8 GB RAM):

| Level | Evidence | What it proves |
|---|---|---|
| 1 | App runs locally (Day 4) + persistence after restart | Python app + SQLite memory |
| 2 | `docker build` + `docker run` (Rancher Desktop **without** Kubernetes, or a lab PC) | containerisation |
| 3 | GitOps repo on GitHub with your edited manifests + `kubectl kustomize` output *or* careful review notes | desired state |
| 4 | Architecture diagram in your own words (Docker → registry → Git → ArgoCD → cluster) | understanding |
| 5 | Annotated screenshots from the instructor demo (clearly labelled "instructor demo") or an approved shared environment | GitOps flow |

Always state clearly what **you ran** and what is **documented/simulated**.

## 11. Windows-specific troubleshooting

| Problem | Fix |
|---|---|
| `kubectl`/`docker` not recognised | open a new PowerShell after Rancher Desktop starts; Rancher adds `%USERPROFILE%\.rd\bin` to PATH |
| WSL errors / "virtualization not enabled" | enable VT-x/AMD-V in BIOS; `wsl --install` (Admin) + reboot; `wsl --update` |
| Rancher Desktop stuck "starting" | Troubleshooting → Reset Kubernetes; give more memory; reboot |
| `docker version` without Server | containerd mode → use `nerdctl`, or switch to dockerd (moby) |
| `InvalidImageName` | uppercase in Docker user name - use lowercase |
| `ImagePullBackOff` | image not pushed / repository private / placeholder not replaced |
| Pod `Pending`, PVC `Pending` | wait; `kubectl get storageclass`; `kubectl -n rootcause describe pvc rootcause-data` |
| `Set-Content` changed line endings | harmless for YAML; `git diff` should show only your intended line |
| Port-forward stops | it ends when its window closes or the pod restarts - run it again |
| ArgoCD cannot read repo | repository must be public; URL ends in `.git`; branch `main`; path `apps/rootcause-copilot` |
| Corporate proxy | set proxy in Rancher Desktop preferences; Docker Hub/GitHub may be blocked - use the fallback path |
| Out of disk | `docker system prune` (removes unused images) |

More: [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## 12. Clean up

```powershell
kubectl delete namespace rootcause argocd
docker volume rm rootcause-data
```
