# Kubernetes manifests (reference copy)

These are the same manifests used in the GitOps starter repository (`rootcause-copilot-gitops/apps/rootcause-copilot`).
In the workshop, **ArgoCD deploys them from the GitOps repository**. You can also apply them directly for testing:

```bash
kubectl apply -k kubernetes/          # Kustomize is built into kubectl
```

| File | Purpose |
|---|---|
| `namespace.yaml` | `rootcause` namespace |
| `configmap.yaml` | Non-secret settings (data directory, upload limit) |
| `pvc.yaml` | 1Gi `ReadWriteOnce` volume for SQLite incident memory; annotated `Prune=false` so ArgoCD never prunes it |
| `deployment.yaml` | 1 replica (SQLite!), `Recreate` strategy, non-root, resources, startup/readiness/liveness probes on `/_stcore/health` |
| `service.yaml` | ClusterIP Service port 80 -> container port 8501 |
| `kustomization.yaml` | Lists the resources and sets the **image name and tag** in one place |
| `groq-secret.template` | Placeholder-only Secret template - **not** listed in Kustomize, never applied as-is |

Before deploying, replace the placeholder `DOCKERHUB_USERNAME` (Docker image names must be lowercase).

## The Groq API key Secret (never committed)

The Deployment reads `GROQ_API_KEY` from a Secret named `rootcause-groq`, marked **optional**: without it the app
still runs and students can paste their own key in the UI. Create it **outside Git**:

macOS / Linux (the key is not echoed and not stored in a file):

```bash
read -s -p "Groq API key: " GROQ_API_KEY; echo
kubectl -n rootcause create secret generic rootcause-groq --from-literal=GROQ_API_KEY="$GROQ_API_KEY"
unset GROQ_API_KEY
```

Windows PowerShell:

```powershell
$secure = Read-Host "Groq API key" -AsSecureString
$plain  = [System.Net.NetworkCredential]::new("", $secure).Password
kubectl -n rootcause create secret generic rootcause-groq --from-literal=GROQ_API_KEY=$plain
Remove-Variable plain, secure
```

File option: copy `groq-secret.template` to `groq.secret.yaml` (the `*.secret.yaml` pattern is git-ignored),
replace the placeholder off-screen, `kubectl apply -f kubernetes/groq.secret.yaml`, then delete the copy.

Never run `kubectl get secret rootcause-groq -o yaml` on a projected screen, and never commit Secret YAML -
base64 is encoding, not encryption. Note: a server-side key is shared by **everyone** who can open the app.
