# 🍎 RootCause Copilot on macOS - Local → Docker → Docker Hub → Kubernetes → ArgoCD

The instructor's demo guide (Apple Silicon M1-M4) and a complete guide for students with a Mac. Commands are
**zsh** (the default macOS shell). Intel Macs work the same - differences are marked **Intel**. Concepts are
explained in [README.md](README.md) and the `docs/` deep dives; the Windows version is [README_WINDOWS.md](README_WINDOWS.md).

> 🔐 **Placeholders.** `DOCKERHUB_USERNAME` = your Docker Hub username (lowercase); `<your-github-user>` = your
> GitHub username. Never put a key, token or password into a tracked file, a commit or a screenshot.

```mermaid
flowchart LR
    A["A. Install"] --> B["B. Clone"] --> C["C. Local"] --> D["D. Docker"] --> E["E. Docker Hub"]
    E --> F["F. Kubernetes"] --> G["G. ArgoCD"] --> H["H. Checklist"]
```

---

## A. Prerequisites

### A1. Tools

[Homebrew](https://brew.sh) is the simplest installer (`brew --version` to check).

| Tool | Mandatory? | Install | Verify |
|---|---|---|---|
| **Git** | ✅ | `xcode-select --install` (Apple's command-line tools) or `brew install git` | `git --version` |
| **Python 3.12** (3.11-3.13 work) | ✅ | `brew install python@3.12` | `python3 --version` |
| **Rancher Desktop** *or* Docker Desktop | ✅ from D | `brew install --cask rancher` · Docker Desktop: installer from docker.com (choose *Apple chip* or *Intel chip*) | `docker version` |
| **kubectl** | ✅ from F (included with Rancher Desktop) | `brew install kubectl` | `kubectl version --client` |
| **ArgoCD CLI** | ⚪ optional (UI is enough) | `brew install argocd` | `argocd version --client` |
| **VS Code** | ⚪ optional | `brew install --cask visual-studio-code` | `code --version` |

### A2. Rancher Desktop or Docker Desktop?

| | **Rancher Desktop** (workshop default) | **Docker Desktop** |
|---|---|---|
| Licence | free, open source | free for education/personal/small business; paid for larger companies |
| Kubernetes | k3s, version selectable | kind or kubeadm |
| Tools included | `docker`/`nerdctl`, `kubectl`, `helm` | `docker`, `kubectl` |
| kubectl context | `rancher-desktop` | `docker-desktop` |

Run **one** of them. Rancher Desktop *Preferences*:

1. **Container Engine → `dockerd (moby)`** (this guide uses the `docker` command).
2. **Kubernetes → Enable ✅**, recent stable version; wait for *running*.
3. **Virtual Machine → Memory ≥ 4 GB** (6 GB with ArgoCD). Apple Silicon: *Emulation → VZ* with **Rosetta**
   enabled helps when building `linux/amd64` images (section E4).
4. **Application → Environment / PATH:** let Rancher Desktop manage PATH (adds `~/.rd/bin`); open a new terminal.

If `docker` talks to the wrong engine: `docker context ls` → `docker context use rancher-desktop`.

---

## B. Clone the repository

**Instructor:** work in your clone of `https://github.com/appars/rootcause-copilot`. **Students:** fork it on
GitHub first (ArgoCD must watch a repository you can push to), then clone the fork.

```zsh
mkdir -p ~/Projects && cd ~/Projects
git clone https://github.com/<your-github-user>/rootcause-copilot.git      # instructor: appars
cd rootcause-copilot
git log --oneline -3
```

---

## C. Run the application locally

```zsh
python3 -m venv .venv
source .venv/bin/activate                    # prompt starts with (.venv)
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m streamlit run app.py               # http://localhost:8501  ·  Ctrl+C stops it
```

- **Configuration:** optional environment variables only (see [.env.example](.env.example)); data goes to `./data_store`.
- **Groq key (optional):** sidebar → **AI Configuration** → paste → **🔌 Connect / Test connection**. The key stays
  in the browser session; never in files or Git.
- **Demo Mode:** works with no key; AI conclusions are predefined and labelled **SIMULATED DEMO RESULTS**.
- **Verify:** sidebar `Release v1.1 · build local`; **🚨 Simulate New Incident Alert** completes; after Ctrl+C and
  a restart the incident is still in **Incident History**.

---

## D. Docker

**Analogy:** the venv is your kitchen; an **image** is a sealed lunchbox (app + Python + libraries); a
**container** is the lunchbox opened; a **volume** is a locker outside the box that keeps the incident memory.

Dockerfile in one glance: official `python:3.12-slim` base → dependencies (cached layer) → code (filtered by
`.dockerignore`) → non-root `USER 10001` → SQLite at `/data` → port 8501 on `0.0.0.0` → `HEALTHCHECK` on
`/_stcore/health`. No key, `.env` or database is ever baked in. Full walkthrough: [docs/DOCKER_DEPLOYMENT.md](docs/DOCKER_DEPLOYMENT.md).

### D1. Build

```zsh
export DOCKERHUB_USERNAME=yourdockerhubname      # lowercase
docker version
docker build -t "$DOCKERHUB_USERNAME/rootcause-copilot:latest" .
docker image inspect "$DOCKERHUB_USERNAME/rootcause-copilot:latest" --format '{{.Os}}/{{.Architecture}}'
```

**Architecture:** on Apple Silicon a plain `docker build` produces **`linux/arm64`**; on an **Intel** Mac (and on
Windows PCs) it produces **`linux/amd64`**. Both are correct for the machine that built them. Do **not** force
`--platform linux/amd64` for your own laptop - it would run under emulation (slower). Section E4 shows how to
publish *both* architectures when other people will pull the image.

### D2. Run, logs, health

```zsh
docker run -d --name rootcause -p 8501:8501 -v rootcause-data:/data "$DOCKERHUB_USERNAME/rootcause-copilot:latest"
docker ps                                                     # (health: starting) → (healthy)
docker logs -f rootcause                                      # Ctrl+C stops following
docker inspect --format '{{.State.Health.Status}}' rootcause  # healthy
curl -fsS http://localhost:8501/_stcore/health; echo          # ok
```

Live AI in the container without typing the key on the command line:

```zsh
read -rs "GROQ_API_KEY?Paste your Groq API key: "; echo; export GROQ_API_KEY
docker rm -f rootcause
docker run -d --name rootcause -p 8501:8501 -v rootcause-data:/data -e GROQ_API_KEY "$DOCKERHUB_USERNAME/rootcause-copilot:latest"
unset GROQ_API_KEY
```

### D3. Persistence, stop, remove

```zsh
# simulate an incident in the browser first
docker rm -f rootcause
docker run -d --name rootcause -p 8501:8501 -v rootcause-data:/data "$DOCKERHUB_USERNAME/rootcause-copilot:latest"
# reload → the incident is still in Incident History

docker stop rootcause && docker start rootcause
docker rm -f rootcause
docker volume rm rootcause-data          # ⚠ deletes incident memory
```

---

## E. Publish to Docker Hub

Convention: **`DOCKERHUB_USERNAME/rootcause-copilot:latest`**.

1. Account at https://hub.docker.com.
2. *Repositories → Create repository* → **`rootcause-copilot`**, **Public**.
3. *Account settings → Personal access tokens* → **Read & Write** token (shown once).
4. Log in - paste the token at the password prompt (Rancher Desktop / Docker Desktop store it in the macOS keychain):

```zsh
docker login -u "$DOCKERHUB_USERNAME"        # Login Succeeded
```

### E1-E3. Build, tag, push, verify (single architecture)

```zsh
docker build -t "$DOCKERHUB_USERNAME/rootcause-copilot:latest" .
# docker tag rootcause-copilot:local "$DOCKERHUB_USERNAME/rootcause-copilot:latest"   # if built under another name
docker push "$DOCKERHUB_USERNAME/rootcause-copilot:latest"
docker rm -f rootcause; docker image rm "$DOCKERHUB_USERNAME/rootcause-copilot:latest"
docker pull "$DOCKERHUB_USERNAME/rootcause-copilot:latest"                            # proves the registry copy works
```

hub.docker.com → your repository → tag `latest` lists the architecture (`linux/arm64` from an M-series Mac).

### E4. Multi-platform image (instructor: required if Windows students pull *your* image)

An `arm64`-only image fails on Intel/AMD machines with `exec format error`. Publish one `latest` tag that contains
both architectures - Docker picks the right one automatically:

```zsh
docker buildx create --name multiarch --use          # once; a builder that can produce multi-platform images
docker buildx build --platform linux/amd64,linux/arm64 \
  -t "$DOCKERHUB_USERNAME/rootcause-copilot:latest" --push .
docker buildx imagetools inspect "$DOCKERHUB_USERNAME/rootcause-copilot:latest"   # lists linux/amd64 and linux/arm64
docker buildx use default                            # back to the normal builder
```

The `amd64` half is built under emulation on Apple Silicon (several minutes). If emulation fails, enable
**VZ + Rosetta** in Rancher Desktop, or run the optional GitHub workflow **Actions → docker-publish**, which builds
both architectures in the cloud once the `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` repository secrets exist.
**Intel** Macs build `amd64` natively; the same command adds `arm64` under emulation.

---

## F. Kubernetes on Rancher Desktop

Objects used: **Namespace** `rootcause` · **Deployment** (1 replica, `Recreate`, 3 probes, non-root) · **Pod** ·
**Service** ClusterIP 80 → 8501 · **ConfigMap** `rootcause-config` · optional **Secret** `rootcause-groq` ·
**PVC** `rootcause-data` 1 Gi at `/data`. Explained in depth: [docs/KUBERNETES_DEPLOYMENT.md](docs/KUBERNETES_DEPLOYMENT.md).

```zsh
kubectl config get-contexts
kubectl config use-context rancher-desktop            # Docker Desktop: docker-desktop
kubectl get nodes                                     # 1 node Ready
kubectl get storageclass                              # local-path (default)

# put your image into the Deployment (macOS sed needs -i '')
sed -i '' "s/DOCKERHUB_USERNAME/$DOCKERHUB_USERNAME/" kubernetes/deployment.yaml
grep -n "image:" kubernetes/deployment.yaml

kubectl kustomize kubernetes/                         # preview - changes nothing
kubectl apply -k kubernetes/
kubectl -n rootcause get pods,deployments,services,pvc
kubectl -n rootcause get pods -w                      # Running 1/1, then Ctrl+C
kubectl -n rootcause logs deploy/rootcause-copilot
kubectl -n rootcause port-forward svc/rootcause-copilot 8501:80     # http://localhost:8501 → build gitops-v1
```

**Optional Groq Secret** (key never written to a file; `read -s` hides it):

```zsh
read -rs "GROQ_KEY?Paste your Groq API key: "; echo
kubectl -n rootcause create secret generic rootcause-groq --from-literal=GROQ_API_KEY="$GROQ_KEY"
unset GROQ_KEY
kubectl -n rootcause rollout restart deployment/rootcause-copilot
```

Base64 in a Secret is **encoding, not encryption** - that is why it never goes to Git.

**Persistence:** simulate an incident → `kubectl -n rootcause delete pod -l app=rootcause-copilot` → wait for the
new pod → restart the port-forward → the incident is still there.

**New `:latest` image:** `kubectl -n rootcause rollout restart deployment/rootcause-copilot` (`imagePullPolicy:
Always` pulls it again) → `kubectl -n rootcause rollout status deployment/rootcause-copilot`.

**Image-pull problems:** `InvalidImageName` = placeholder still in the YAML · `ErrImagePull`/`ImagePullBackOff` =
not pushed, typo or private repository · `exec format error` in the logs = architecture mismatch (E4).
`kubectl -n rootcause describe pod -l app=rootcause-copilot` shows the reason under *Events*.

---

## G. ArgoCD GitOps (same repository)

GitHub holds the code and the YAML; Docker Hub holds the image; ArgoCD applies `kubernetes/` from the `main`
branch of **this** repository - there is no separate GitOps repository. Details: [docs/ARGOCD_GITOPS.md](docs/ARGOCD_GITOPS.md).

```zsh
kubectl create namespace argocd
kubectl apply -n argocd --server-side --force-conflicts \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl -n argocd get pods -w                                   # all Running, then Ctrl+C

kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d; echo
kubectl -n argocd port-forward svc/argocd-server 8080:443       # second terminal tab - keep open
```

Open **https://localhost:8080**, accept the self-signed certificate, log in as **admin**.
Optional CLI: `argocd login localhost:8080 --username admin --insecure`.

**Commit the desired state** (ArgoCD deploys only what is in Git):

- `kubernetes/deployment.yaml` - your Docker Hub username (done above).
- `argocd/rootcause-copilot-application.yaml` - students: `repoURL: https://github.com/<your-github-user>/rootcause-copilot.git`
  (the instructor keeps `appars`).

```zsh
git add kubernetes/deployment.yaml argocd/rootcause-copilot-application.yaml
git commit -m "Deploy my image with ArgoCD"
git push
```

**Hand over from manual to ArgoCD** - nothing needs deleting; ArgoCD adopts the same-named resources. Afterwards
change only Git (no more `kubectl apply -k`).

```zsh
kubectl apply -f argocd/rootcause-copilot-application.yaml
kubectl -n argocd get applications                    # Synced / Healthy
```

| Demo | Commands | Expected |
|---|---|---|
| **Git change → sync** | edit `value: "gitops-v1"` → `"gitops-v2"` in `kubernetes/deployment.yaml`; `git commit -am "Release label gitops-v2" && git push`; **Refresh** | OutOfSync → Synced; new pod; sidebar **build gitops-v2** (restart the port-forward) |
| **Self-heal** | `kubectl -n rootcause delete service rootcause-copilot` · `kubectl -n rootcause scale deployment rootcause-copilot --replicas=0` | Service re-created, replicas back to 1 within seconds |
| **Rollback** | `git revert HEAD --no-edit && git push` | syncs back to **build gitops-v1** (UI rollback is disabled while auto-sync is on - by design) |
| **New image** | push `latest` (E), then `kubectl -n rootcause rollout restart deployment/rootcause-copilot` or UI → Deployment **⋮ → Restart** | new pod with the new image; still Synced |
| **History** | `argocd app history rootcause-copilot` | one entry per synced Git revision |

Policy: automated sync ✅ · self-heal ✅ · prune ❌ (conservative) · PVC and Namespace annotated
`Prune=false,Delete=false`, so ArgoCD never deletes incident memory.

> **Instructor before class:** commit your real Docker Hub username into `kubernetes/deployment.yaml` of the
> course repository (or demo from a fork), and publish a multi-platform `latest` (E4) so Windows students can
> pull your image. Students keep the placeholder until they replace it with their own username.

---

## H. Verification checklist

| # | Check | ✅ |
|---|---|---|
| 1 | Local app, sidebar `build local`, incident survives restart | ☐ |
| 2 | Image built; `docker ps` shows `(healthy)`; data survives container re-creation | ☐ |
| 3 | Image on Docker Hub (instructor: `imagetools inspect` lists amd64 + arm64); `docker pull` works | ☐ |
| 4 | `kubectl -n rootcause get pods,svc,pvc`: Running 1/1, Bound; app shows `build gitops-v1` | ☐ |
| 5 | Data survives pod deletion | ☐ |
| 6 | ArgoCD Synced + Healthy; Git change → `gitops-v2`; self-heal; `git revert` → `gitops-v1` | ☐ |
| 7 | `git grep -n gsk_` finds nothing; no secrets on screenshots | ☐ |

---

## I. macOS troubleshooting

| Problem | Fix |
|---|---|
| `xcrun: error: invalid active developer path` | `xcode-select --install` |
| `python3` is an old version | `brew install python@3.12`, then `python3.12 -m venv .venv` |
| `docker: command not found` | open a new terminal; Rancher Desktop → *Preferences → Application → Environment* manages PATH (`~/.rd/bin`) |
| `Cannot connect to the Docker daemon` | start Rancher Desktop; `docker context use rancher-desktop`; engine must be `dockerd (moby)` |
| `exec format error` (pod or container) | image built for another CPU - publish multi-platform (E4) |
| amd64 build fails / very slow on Apple Silicon | enable VZ + Rosetta in Rancher Desktop, or use the *docker-publish* workflow |
| `base64: invalid option -- d` (old macOS) | use `base64 -D` |
| Port 8501 or 8080 busy | `lsof -i :8501` → stop it, or forward another port (`8502:80`, `8081:443`) |
| `sed: 1: "kubernetes/...": command c expects \` | macOS `sed` needs `-i ''` (as shown above) |
| Rancher Desktop asks for an admin password | it configures networking/PATH - allow it, or disable *Administrative Access* (some features need it) |
| Port-forward stopped | the pod was replaced - run it again |
| ArgoCD `ComparisonError` | `repoURL` typo / private fork; branch `main`; path `kubernetes` |

Everything else: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).
