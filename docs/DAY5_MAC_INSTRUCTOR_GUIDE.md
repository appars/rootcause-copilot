# Day 5 Instructor Guide (macOS) - RootCause Copilot v1.1: Docker → Registry → Kubernetes → GitOps → ArgoCD

> "Today, we made our agent more intelligent, reliable and controlled. Tomorrow, we will take this application
> beyond our laptop -- package it using Docker, deploy it on Kubernetes and explore GitOps with ArgoCD."
> *(closing line of Day 4 - open Day 5 by repeating it)*

This guide is for the **instructor's Mac**. Students follow the Windows homework guide
([DAY5_WINDOWS_DEPLOYMENT_HOMEWORK.md](DAY5_WINDOWS_DEPLOYMENT_HOMEWORK.md)).

**Versions checked (November 2026):** Argo CD stable = **v3.6.1** (`VERSION` file on the `stable` branch);
Argo CD's install instructions require `kubectl apply --server-side --force-conflicts` because some CRDs exceed
the client-side annotation size limit. Rancher Desktop offers two container engines - **containerd** (use
`nerdctl`) and **dockerd/moby** (use `docker`) - and runs k3s. Re-check versions on the morning of the session.

> **Honesty note for the instructor:** the v1.1 manifests were validated against the Kubernetes v1.33 JSON schemas
> and the Argo CD Application CRD, but the Docker build, the live cluster and the ArgoCD steps were **not executed**
> in the build environment (no container runtime or cluster there). Do a full dry run on your Mac before class.

---

## 0. The story to tell (2 minutes)

```text
Python / Streamlit app ─► Docker image ─► Registry (Docker Hub) ─► GitOps repo (GitHub) ─► ArgoCD watches Git ─► Kubernetes (Rancher Desktop) ─► running RootCause Copilot
```

| Piece | Responsibility | One-liner for students |
|---|---|---|
| Docker | package app + dependencies into an image | "works on my laptop" becomes "works anywhere" |
| Registry | store and distribute images by tag | the image's address book |
| Kubernetes | run and heal containers, storage, networking | the operating system of the cluster |
| Git (GitOps repo) | the **desired state** (YAML) | what *should* be running |
| ArgoCD | reconciles cluster ← Git, continuously | makes reality match Git |

## 1a. Install and start Rancher Desktop (once)

1. Download Rancher Desktop for macOS from rancherdesktop.io (choose the Apple Silicon or Intel build) and drag it to
   *Applications*. Start it.
2. First-run dialog: **Enable Kubernetes** (keep the suggested stable version) and choose the container engine.
   This guide's main path uses **dockerd (moby)** so commands read `docker ...`; the containerd path is in §3.4.
3. *Preferences → Virtual Machine*: at least 4 CPUs and 8 GB memory. *Preferences → Application → PATH*: let it
   manage PATH (installs `kubectl`, `docker`, `nerdctl`, `rdctl` into `~/.rd/bin`). Open a **new** terminal.
4. Wait until the status bar shows Kubernetes is running (the first start downloads images; it can take minutes).

## 1. Checklist - the day before

- [ ] Rancher Desktop installed and updated; **Kubernetes enabled**; VM: ≥ 4 CPU, ≥ 8 GB RAM.
- [ ] Container engine chosen (this guide's main path uses **dockerd (moby)** so commands read `docker ...`).
- [ ] Docker Hub account. Create the repository: hub.docker.com → **Repositories → Create repository** → name
      `rootcause-copilot`, visibility **Public** (so the cluster can pull without credentials). Create an
      **access token** (*Account settings → Personal access tokens*) and use it instead of your password for `docker login`.
- [ ] GitHub: application repository `rootcause-copilot` and **public** GitOps repository `rootcause-copilot-gitops`.
- [ ] **Backup images already pushed:** `day4-v1` and `day5-v2` (multi-arch, see §3.3).
- [ ] ArgoCD installed once and removed again (to know the timing), or left installed as a fallback.
- [ ] Browser tabs: ArgoCD UI, Docker Hub repo, GitHub GitOps repo.
- [ ] A Groq key ready to create the Secret **off-screen** (optional - the app works in Demo Mode without it).
- [ ] Terminal font enlarged; notifications off; no secrets in shell history on the projected screen.

Set placeholders once per terminal (replace with your real values, lowercase for Docker):

```bash
export DOCKERHUB_USER=<DOCKERHUB_USERNAME>
export GH_USER=<GITHUB_USERNAME>
export IMG=docker.io/$DOCKERHUB_USER/rootcause-copilot
```

## 2. Environment checks (do them live - it teaches good habits)

```bash
uname -m                              # arm64 = Apple Silicon, x86_64 = Intel
rdctl version                         # Rancher Desktop CLI
rdctl list-settings | grep -A2 '"containerEngine"'   # look for "name": "moby" or "containerd"

kubectl config get-contexts
kubectl config use-context rancher-desktop          # never deploy to the wrong cluster
kubectl config current-context                      # must print: rancher-desktop
kubectl get nodes -o wide                           # 1 node, Ready
kubectl get storageclass                            # expect local-path (default)
```

Container engine:

```bash
docker context ls          # the active context should be rancher-desktop's
docker version             # BOTH "Client" and "Server" sections must appear
```

- **dockerd (moby)** selected → `docker build/run/push` work and locally built images are visible to k3s.
- **containerd** selected → there is **no Docker daemon**; `docker version` shows no Server. Use `nerdctl`
  with the same flags (`nerdctl build`, `nerdctl run`, `nerdctl push`). To make a locally built image visible to
  Kubernetes without a registry, add `--namespace k8s.io`. In this GitOps demo the cluster pulls from Docker Hub,
  so the registry path is what matters.
- Switch engine: Rancher Desktop → Preferences → Container Engine (the VM restarts).

Explain: *installing Rancher Desktop does not guarantee a Docker daemon - check, don't assume.*

## 3. Build, run and push the image

### 3.1 Build (single architecture, fast)

```bash
cd rootcause-copilot
docker build --build-arg APP_VERSION=day4-v1 -t $IMG:day4-v1 .
docker image ls $IMG
docker image inspect $IMG:day4-v1 --format '{{.Os}}/{{.Architecture}}'   # e.g. linux/arm64 on Apple Silicon
docker history $IMG:day4-v1 | head      # talk about layers: base, user, requirements, code
```

Teaching points: base image `python:3.12-slim`; dependency layer cached until `requirements.txt` changes;
non-root user `10001`; `.dockerignore` keeps `.env`, `data_store/`, tests and docs out; `APP_VERSION` is baked in
and shown in the app sidebar - that makes the later rollout visible.

### 3.2 Run locally

```bash
docker run --rm -d --name rootcause -p 8501:8501 -v rootcause-data:/data $IMG:day4-v1
docker ps
curl -s http://localhost:8501/_stcore/health ; echo        # expected: ok
open http://localhost:8501
```

Create an investigation, close it, then show persistence across containers:

```bash
docker rm -f rootcause
docker run --rm -d --name rootcause -p 8501:8501 -v rootcause-data:/data $IMG:day4-v1
# Incident History still shows the incident (named volume)
docker rm -f rootcause
```

### 3.3 Push, verify the pull - and why architecture matters

```bash
docker login                         # user name + ACCESS TOKEN, typed off-screen; never in a script or screenshot
docker push $IMG:day4-v1
# Verify the registry really has it: delete the local copy and pull it back
docker image rm $IMG:day4-v1
docker pull $IMG:day4-v1
docker image inspect $IMG:day4-v1 --format '{{.Id}} {{.Architecture}}'
```

Your Mac's k3s pulls an image for **its own** architecture. Students on Intel/AMD Windows laptops need
`linux/amd64`. Build both with buildx (check `docker buildx version` first):

```bash
docker buildx create --name rc-builder --use 2>/dev/null || docker buildx use rc-builder
docker buildx build --platform linux/amd64,linux/arm64 \
  --build-arg APP_VERSION=day4-v1 -t $IMG:day4-v1 --push .
docker buildx build --platform linux/amd64,linux/arm64 \
  --build-arg APP_VERSION=day5-v2 -t $IMG:day5-v2 --push .
docker buildx imagetools inspect $IMG:day4-v1      # lists both platforms
```

### 3.4 If Rancher Desktop uses **containerd** (no Docker daemon)

`docker version` shows no *Server* section → use `nerdctl` (bundled with Rancher Desktop) with the same flags:

```bash
nerdctl build --build-arg APP_VERSION=day4-v1 -t $IMG:day4-v1 .
nerdctl run --rm -d --name rootcause -p 8501:8501 -v rootcause-data:/data $IMG:day4-v1
nerdctl login                                    # access token, off-screen
nerdctl push $IMG:day4-v1
# multi-arch (slower, emulated): nerdctl build --platform=amd64,arm64 ... then nerdctl push --all-platforms ...
# make a LOCAL image visible to k3s without a registry: add --namespace k8s.io to the build
```

Images built under one engine are not visible under the other; switching engines restarts the VM. The GitOps demo
pulls from Docker Hub, so either engine works as long as the image is pushed.

Never deploy `latest`: Git would not change when the image changes, so ArgoCD could not show or roll back the change.

## 4. Explain the Kubernetes resources (5 minutes, open the files)

`kubernetes/` (identical to `rootcause-copilot-gitops/apps/rootcause-copilot/`):

| File | Say this |
|---|---|
| `namespace.yaml` | isolation boundary `rootcause` |
| `configmap.yaml` | non-secret settings (`ROOTCAUSE_DATA_DIR=/data`) |
| Secret (not in Git!) | `GROQ_API_KEY`, created with `kubectl`, referenced as **optional** |
| `pvc.yaml` | 1Gi `ReadWriteOnce`; on k3s the default `local-path` class binds when the pod is scheduled |
| `deployment.yaml` | **1 replica** + `Recreate` because SQLite on one RWO volume is not a shared database; non-root; requests/limits; startup/readiness/liveness probes on `/_stcore/health` |
| `service.yaml` | stable name; port 80 → container port 8501 |
| `kustomization.yaml` | the **one place** where the image tag changes |

ConfigMap vs Secret: both inject configuration; Secrets are for sensitive values, have tighter RBAC and are
not printed by default - but base64 is not encryption, so never commit them.

Optional pre-check: `kubectl apply -k kubernetes/ --dry-run=server` (after replacing the placeholder).

v1.1 hardening worth pointing at in `deployment.yaml`: `seccompProfile: RuntimeDefault`,
`allowPrivilegeEscalation: false`, `capabilities: drop [ALL]`, `automountServiceAccountToken: false`.

### 4.1 (Optional) Direct deployment without ArgoCD - a smoke test

Shows plain Kubernetes first; ArgoCD will later manage the same resources.

```bash
sed -i '' "s/DOCKERHUB_USERNAME/$DOCKERHUB_USER/g" kubernetes/kustomization.yaml kubernetes/deployment.yaml   # local copy only
kubectl apply -k kubernetes/
kubectl -n rootcause get pods,svc,pvc            # pod Running, PVC Bound, Service ClusterIP
kubectl -n rootcause port-forward svc/rootcause-copilot 8501:80     # open http://localhost:8501
kubectl delete -k kubernetes/                    # clean up before the GitOps part (also deletes the PVC data)
git checkout kubernetes/                         # undo the local placeholder edit
```

## 5. Namespace and Secret (off-screen for the key)

```bash
kubectl create namespace rootcause
# switch the projector to a blank screen for the next 3 lines
read -s -p "Groq API key: " GROQ_API_KEY; echo
kubectl -n rootcause create secret generic rootcause-groq --from-literal=GROQ_API_KEY="$GROQ_API_KEY"
unset GROQ_API_KEY
kubectl -n rootcause get secret rootcause-groq          # shows only name/type/age - safe to project
```

File-based alternative: copy `kubernetes/groq-secret.template` to `kubernetes/groq.secret.yaml` (git-ignored),
fill in the key off-screen, `kubectl apply -f kubernetes/groq.secret.yaml`, then delete the file.

Skip the Secret entirely if you prefer: the pod starts anyway (`optional: true`) and users paste their own key.
Remind students: a server-side key is shared by everyone who can open the app.

## 6. Install ArgoCD

```bash
kubectl create namespace argocd
kubectl apply -n argocd --server-side --force-conflicts \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/v3.6.1/manifests/install.yaml
# (latest stable instead of the pinned version: replace v3.6.1 with "stable")

kubectl -n argocd rollout status deploy/argocd-server --timeout=300s
kubectl -n argocd rollout status deploy/argocd-repo-server --timeout=300s
kubectl -n argocd get pods            # all Running (application-controller is a StatefulSet)
```

UI access (keep this terminal open):

```bash
kubectl port-forward svc/argocd-server -n argocd 8080:443
```

Open **https://localhost:8080** and accept the self-signed certificate warning (explain why it appears).
Initial admin password (**not on the projector**):

```bash
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d; echo
# or, with the argocd CLI (brew install argocd):  argocd admin initial-password -n argocd
```

Log in as `admin`. Tour: Applications, Settings → Repositories, the resource tree, Sync/Refresh, History.

## 7. Prepare the GitOps repository

```bash
cp -R ../rootcause-copilot-gitops ~/rootcause-copilot-gitops && cd ~/rootcause-copilot-gitops
sed -i '' "s/DOCKERHUB_USERNAME/$DOCKERHUB_USER/g" apps/rootcause-copilot/kustomization.yaml apps/rootcause-copilot/deployment.yaml
sed -i '' "s/GITHUB_USERNAME/$GH_USER/g" argocd/rootcause-copilot-application.yaml
grep -n "newName\|newTag" apps/rootcause-copilot/kustomization.yaml
grep -n repoURL argocd/rootcause-copilot-application.yaml
git init -b main && git add . && git commit -m "RootCause Copilot desired state day4-v1"
git remote add origin https://github.com/$GH_USER/rootcause-copilot-gitops.git
git push -u origin main
```

(`sed -i ''` is the macOS form. A public repository needs no ArgoCD credentials.)

## 7a. Connect the GitOps repository in ArgoCD

- **Public repository (recommended for the workshop):** nothing to configure - ArgoCD can read it anonymously.
  Show *Settings → Repositories → CONNECT REPO* → *VIA HTTPS* → URL `https://github.com/$GH_USER/rootcause-copilot-gitops.git`
  → **CONNECT**; the connection status should be **Successful**.
- **Private repository:** connect with a GitHub fine-grained token that has read-only access, typed off-screen
  (UI as above with username + token, or `argocd repo add <url> --username <user> --password <token>`).
  ArgoCD stores it as a Secret in the `argocd` namespace - never in Git.

## 8. Create the Application and do a MANUAL first sync

```bash
kubectl apply -f argocd/rootcause-copilot-application.yaml
kubectl -n argocd get applications            # SYNC STATUS: OutOfSync, HEALTH: Missing
```

In the UI open **rootcause-copilot** → **SYNC** → **SYNCHRONIZE**. (CLI: `argocd app sync rootcause-copilot`.)
Watch the tree: Namespace → ConfigMap, PVC, Service, Deployment → ReplicaSet → Pod.

## 9. Verify

```bash
kubectl -n rootcause get deploy,rs,pods,svc,pvc
kubectl -n rootcause rollout status deploy/rootcause-copilot
kubectl -n rootcause describe pod -l app=rootcause-copilot | sed -n '/Events/,$p'
kubectl -n rootcause logs deploy/rootcause-copilot --tail=20
kubectl -n rootcause port-forward svc/rootcause-copilot 8501:80       # new terminal
```

Open **http://localhost:8501** - sidebar shows **Release v1.1 · build day4-v1**. Expected (example, not captured output):
`Synced` + `Healthy` in ArgoCD; pod `1/1 Running`; PVC `Bound`.

**Persistence:** run and close an investigation, then
`kubectl -n rootcause delete pod -l app=rootcause-copilot` → a new pod starts → Incident History still has it.

## 10. Turn on Auto-Sync (and show self-healing) - with care about pruning

```bash
kubectl -n argocd patch application rootcause-copilot --type merge --patch-file argocd/autosync-patch.json
kubectl -n rootcause scale deploy/rootcause-copilot --replicas=0     # simulate manual drift
kubectl -n rootcause get deploy -w                                    # ArgoCD (selfHeal) restores replicas: 1
```

**Pruning caution:** `prune: true` deletes cluster resources that disappear from Git. Deleting `pvc.yaml` from Git
would delete the incident-memory volume. v1.1 protects it with the annotation
`argocd.argoproj.io/sync-options: Prune=false` on the PVC - show it, and explain why stateful resources deserve it.

## 11. Change desired state in Git: day4-v1 → day5-v2

Two options - choose before class:

- **A (clearest OutOfSync):** temporarily disable auto-sync in the UI (*App Details → Disable Auto-Sync*).
- **B (fully automatic):** keep auto-sync on; click **Refresh** right after the push to see OutOfSync briefly.

```bash
cd ~/rootcause-copilot-gitops
sed -i '' 's/newTag: day4-v1/newTag: day5-v2/' apps/rootcause-copilot/kustomization.yaml
git diff
git commit -am "Release day5-v2" && git push
```

In ArgoCD click **Refresh** (ArgoCD also polls Git periodically, by default every few minutes) → status
**OutOfSync**; the diff shows only the image tag. Option A: click **Sync**. Then:

```bash
kubectl -n rootcause rollout status deploy/rootcause-copilot
kubectl -n rootcause get pods -w          # Recreate: old pod terminates, then the new one starts
```

Reconnect the port-forward if it dropped; the sidebar shows **build day5-v2**; incident history is still there (PVC).
Re-enable auto-sync if you used option A.

## 12. Roll back through Git

```bash
git revert --no-edit HEAD && git push
```

ArgoCD syncs back to `day4-v1`. Explain: *Git history is the source of truth - the rollback is reviewable,
auditable and repeatable.* (ArgoCD's own History → Rollback button is disabled while auto-sync is on for exactly
this reason.)

## 13. What would change for production (3 minutes)

- Managed PostgreSQL instead of SQLite → more replicas, `RollingUpdate`, PodDisruptionBudget, HPA.
- Ingress + TLS + SSO in front of the app; RBAC for approvals; network policies.
- Secrets from a secret manager (External Secrets / Sealed Secrets), never `kubectl create` by hand.
- CI pipeline: tests → image build → vulnerability scan → signed image → automatic PR to the GitOps repo.
- Environments (dev/staging/prod) as Kustomize overlays; ArgoCD projects with restricted destinations.
- Observability: metrics, logs, traces - and a *real*, secured alert webhook.

## 14. Troubleshooting

| Symptom | Check / fix |
|---|---|
| `docker version` has no Server section | engine is containerd → use `nerdctl`, or switch to dockerd (moby) |
| `ErrImagePull` / `ImagePullBackOff` | placeholder not replaced? image private? tag pushed? `kubectl -n rootcause describe pod ...` |
| `InvalidImageName` | uppercase letters in the image name (Docker names must be lowercase) |
| `exec format error` | image built for the wrong CPU architecture → buildx multi-arch (§3.3) |
| Pod `Pending`, PVC `Pending` | `kubectl get storageclass`; k3s `local-path` binds when the pod is scheduled (normal briefly) |
| Readiness probe failing | first start takes ~20-40 s; `kubectl logs`; startupProbe allows 150 s |
| `CreateContainerConfigError` | ConfigMap name typo (the Secret is optional and cannot cause this) |
| ArgoCD `ComparisonError` / repo not accessible | repo private or URL typo; path must be `apps/rootcause-copilot` |
| ArgoCD stays OutOfSync after push | click **Refresh**; check `targetRevision: main` and the pushed branch |
| Browser cannot reach 8080/8501 | port-forward terminal closed - restart it |
| Wrong cluster | `kubectl config current-context` must be `rancher-desktop` |

## 15. Fallback plan

| Failure | Fallback |
|---|---|
| Conference Wi-Fi blocks Docker Hub | use pre-pulled images (`docker pull` both tags before class); with dockerd the local image is visible to k3s |
| GitHub unreachable from ArgoCD | `kubectl apply -k kubernetes/` to show the Kubernetes part; explain GitOps with the diagrams |
| ArgoCD install slow | keep a pre-installed ArgoCD from the dry run |
| Rancher Desktop broken | run the container with `docker run` and walk through YAML + ArgoCD screenshots from the dry run |
| Groq unavailable | Demo Mode - it is clearly labelled and fully functional |

## 16. Instructor checklist (during the session)

- [ ] Context = `rancher-desktop` shown on screen
- [ ] Build → run → health `ok` → push
- [ ] Secret created off-screen (or skipped)
- [ ] ArgoCD installed, UI open, password not projected
- [ ] Manual sync → Healthy; app open; version day4-v1
- [ ] Pod deleted → memory persists
- [ ] Auto-sync + self-heal demo
- [ ] Tag change → OutOfSync → rollout → version day5-v2
- [ ] `git revert` → back to day4-v1
- [ ] Production differences discussed; homework announced

### Cleanup after class

```bash
kubectl delete -f argocd/rootcause-copilot-application.yaml     # removes the Application object only*
kubectl delete namespace rootcause argocd                         # removes the app resources, PVC data and ArgoCD
# *ArgoCD deletes the deployed resources itself only if the Application has the resources finalizer.
docker volume rm rootcause-data
```
