# ArgoCD configuration

- `rootcause-copilot-application.yaml` - the ArgoCD `Application` (manual sync first). Replace `GITHUB_USERNAME`.
- `autosync-patch.json` - enables Auto-Sync (`prune` + `selfHeal`) after the first manual sync:

```bash
kubectl -n argocd patch application rootcause-copilot --type merge --patch-file argocd/autosync-patch.json
```

The same files are included in the GitOps starter repository (`rootcause-copilot-gitops/argocd/`).
Full walkthrough: `docs/DAY5_MAC_INSTRUCTOR_GUIDE.md` (instructor, macOS) and
`docs/DAY5_WINDOWS_DEPLOYMENT_HOMEWORK.md` (students, Windows).
