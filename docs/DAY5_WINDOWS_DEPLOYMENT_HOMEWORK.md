# Day 5 Windows Deployment Homework - moved

The step-by-step Windows guide is now **[README_WINDOWS.md](../README_WINDOWS.md)** in the repository root
(PowerShell: local run → Docker → Docker Hub → Kubernetes on Rancher Desktop → ArgoCD → checklist → troubleshooting).

What to submit, the fallback path for low-resource laptops and the marking scheme:
**[docs/HOMEWORK_SUBMISSION.md](HOMEWORK_SUBMISSION.md)**.

Since the Day 5 deployment-ready release there is **no separate GitOps repository**: fork
`https://github.com/appars/rootcause-copilot`, and ArgoCD watches the `kubernetes/` folder of your fork.
The image convention is `DOCKERHUB_USERNAME/rootcause-copilot:latest`.
