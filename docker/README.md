# Docker quick reference

The `Dockerfile` and `.dockerignore` live in the repository root (the build context is the whole app).
Step-by-step: [README_WINDOWS.md](../README_WINDOWS.md#d-docker) · [README_MAC.md](../README_MAC.md#d-docker) ·
concepts and design: [docs/DOCKER_DEPLOYMENT.md](../docs/DOCKER_DEPLOYMENT.md).

Replace `DOCKERHUB_USERNAME` with your Docker Hub username (lowercase). Course convention: one tag, `latest`.

```bash
docker build -t DOCKERHUB_USERNAME/rootcause-copilot:latest .
docker run -d --name rootcause -p 8501:8501 -v rootcause-data:/data DOCKERHUB_USERNAME/rootcause-copilot:latest
docker ps                                   # (healthy) after ~30 s
docker logs -f rootcause
docker login -u DOCKERHUB_USERNAME          # paste a Docker Hub access token, not your password
docker push DOCKERHUB_USERNAME/rootcause-copilot:latest

# instructor: one tag for Apple Silicon AND Intel/AMD machines
docker buildx build --platform linux/amd64,linux/arm64 -t DOCKERHUB_USERNAME/rootcause-copilot:latest --push .
```

| Build argument | Default | Purpose |
|---|---|---|
| `PYTHON_IMAGE` | `python:3.12-slim` | base image; only change it to a mirror of the same official image |
| `APP_VERSION` | `latest` | build label shown in the sidebar (Kubernetes overrides it with `ROOTCAUSE_APP_VERSION`) |

Rancher Desktop in **containerd** mode: use `nerdctl` with the same flags.
