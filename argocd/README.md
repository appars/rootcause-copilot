# ArgoCD Application

`rootcause-copilot-application.yaml` tells ArgoCD: *keep namespace `rootcause` equal to the `kubernetes/` folder of
the `main` branch of this repository.* One repository - no separate GitOps repository.

| Field | Value | Change it? |
|---|---|---|
| `source.repoURL` | `https://github.com/appars/rootcause-copilot.git` | **students:** your fork's URL |
| `source.targetRevision` / `path` | `main` / `kubernetes` | no |
| `destination` | in-cluster (`https://kubernetes.default.svc`), namespace `rootcause` | no |
| `syncPolicy.automated` | `selfHeal: true`, `prune: false` | see below |
| `syncOptions` | `CreateNamespace=true` | no |
| `revisionHistoryLimit` | `5` | no |

```bash
kubectl apply -f argocd/rootcause-copilot-application.yaml
kubectl -n argocd get applications          # Synced / Healthy
```

**Why `prune: false`?** If a manifest is removed from Git, ArgoCD only marks the resource as orphaned instead of
deleting it - nothing disappears by accident in a classroom. The PVC and Namespace are additionally annotated
`Prune=false,Delete=false`, so even enabling pruning, or deleting the Application, never deletes incident memory.
To enable pruning deliberately (e.g. after renaming a resource), set `prune: true` in Git and commit.

**Manual → ArgoCD:** resources created earlier with `kubectl apply -k kubernetes/` are adopted (same names);
afterwards change only Git. **Removing the Application** (`kubectl -n argocd delete application rootcause-copilot`)
leaves the running resources in place.

Walkthrough: [README_WINDOWS.md](../README_WINDOWS.md#g-argocd-gitops) · [README_MAC.md](../README_MAC.md#g-argocd-gitops-same-repository) ·
concepts: [docs/ARGOCD_GITOPS.md](../docs/ARGOCD_GITOPS.md).
