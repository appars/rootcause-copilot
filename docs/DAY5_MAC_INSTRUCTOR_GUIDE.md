# Day 5 Instructor Guide (macOS) - moved

The Day 5 instructor walkthrough is now **[README_MAC.md](../README_MAC.md)** in the repository root.

What changed in the Day 5 deployment-ready release:

| Before | Now |
|---|---|
| two repositories (`rootcause-copilot` + `rootcause-copilot-gitops`) | **one** repository; ArgoCD watches `kubernetes/` on `main` |
| tags `day4-v1` / `day5-v2` set in `kustomization.yaml` | one tag, `DOCKERHUB_USERNAME/rootcause-copilot:latest`, set in `deployment.yaml` |
| GitOps demo = image tag change | GitOps demo = release label `ROOTCAUSE_APP_VERSION` `gitops-v1` → `gitops-v2`, rollback with `git revert` |
| manual sync, then an auto-sync patch | automated sync + self-heal from the start, pruning off, PVC/Namespace protected |

Concepts: [docs/DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md) · [docs/KUBERNETES_DEPLOYMENT.md](KUBERNETES_DEPLOYMENT.md) ·
[docs/ARGOCD_GITOPS.md](ARGOCD_GITOPS.md).
