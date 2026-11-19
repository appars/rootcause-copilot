# Kubernetes manifests

One set of manifests for **both** deployment paths - manual (`kubectl apply -k kubernetes/`) and GitOps (ArgoCD
watches this folder, see [../argocd/](../argocd/README.md)). Step-by-step: [README_WINDOWS.md](../README_WINDOWS.md#f-kubernetes-on-rancher-desktop) ·
[README_MAC.md](../README_MAC.md#f-kubernetes-on-rancher-desktop) · design: [docs/KUBERNETES_DEPLOYMENT.md](../docs/KUBERNETES_DEPLOYMENT.md).

```bash
kubectl kustomize kubernetes/        # preview the exact YAML
kubectl apply -k kubernetes/         # manual deployment (before handing over to ArgoCD)
kubectl -n rootcause get pods,svc,pvc
kubectl -n rootcause port-forward svc/rootcause-copilot 8501:80
```

| File | Purpose |
|---|---|
| `namespace.yaml` | namespace `rootcause`; ArgoCD `Prune=false,Delete=false` (deleting it would delete the PVC) |
| `configmap.yaml` | non-secret settings: `ROOTCAUSE_DATA_DIR=/data`, upload limit |
| `pvc.yaml` | 1 Gi `ReadWriteOnce` volume for SQLite; ArgoCD `Prune=false,Delete=false` |
| `deployment.yaml` | **the one line to edit: the image** · 1 replica + `Recreate` (SQLite) · `imagePullPolicy: Always` (`latest`) · non-root, no capabilities, no service-account token · 3 probes · resources · `ROOTCAUSE_APP_VERSION` release label for the GitOps demo |
| `service.yaml` | ClusterIP, port 80 → container port `http` (8501) |
| `kustomization.yaml` | lists the five resources (no Secret) |
| `groq-secret.template` | placeholder-only Secret template - not in Kustomize, never applied as-is |

**Before deploying:** replace `DOCKERHUB_USERNAME` in `deployment.yaml` (lowercase; uppercase gives `InvalidImageName`).
**New image with the same `latest` tag:** `kubectl -n rootcause rollout restart deployment/rootcause-copilot`.

## The optional Groq API key Secret (never committed)

The Deployment reads `GROQ_API_KEY` from Secret `rootcause-groq`, marked **optional** - without it the app runs
and users paste their own key in the sidebar. Create it outside Git, after the namespace exists:

macOS (zsh) / Linux (bash) - the key is not echoed and not written to a file:

```bash
printf "Groq API key: "; read -rs GROQ_KEY; echo
kubectl -n rootcause create secret generic rootcause-groq --from-literal=GROQ_API_KEY="$GROQ_KEY"
unset GROQ_KEY
kubectl -n rootcause rollout restart deployment/rootcause-copilot
```

Windows PowerShell:

```powershell
$secure = Read-Host "Groq API key" -AsSecureString
$key = [System.Net.NetworkCredential]::new("", $secure).Password
kubectl -n rootcause create secret generic rootcause-groq --from-literal=GROQ_API_KEY=$key
Remove-Variable key, secure
kubectl -n rootcause rollout restart deployment/rootcause-copilot
```

File option: copy `groq-secret.template` to `groq.secret.yaml` (`*.secret.yaml` is git-ignored), replace the
placeholder off-screen, `kubectl apply -f kubernetes/groq.secret.yaml`, delete the copy.

**Base64 is encoding, not encryption.** Never run `kubectl get secret rootcause-groq -o yaml` on a projected
screen and never commit Secret YAML. ArgoCD does not touch this Secret (it is not in Git, and pruning is off).
A server-side key is shared by **everyone** who can open the app.
