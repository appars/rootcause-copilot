# Docker quick reference

The `Dockerfile` lives in the repository root (so the build context is the whole app).
Replace `<DOCKERHUB_USERNAME>` with your Docker Hub user name (lowercase).

```bash
# build (version is baked into the image and shown in the app sidebar)
docker build --build-arg APP_VERSION=day4-v1 -t <DOCKERHUB_USERNAME>/rootcause-copilot:day4-v1 .

# run locally with a named volume for SQLite memory
docker run --rm -p 8501:8501 -v rootcause-data:/data <DOCKERHUB_USERNAME>/rootcause-copilot:day4-v1

# push
docker login
docker push <DOCKERHUB_USERNAME>/rootcause-copilot:day4-v1
```

With Rancher Desktop in **containerd** mode use `nerdctl` instead of `docker` (same flags), and add
`--namespace k8s.io` if you want the image visible to the local cluster without a registry.
Multi-architecture images (Apple Silicon + Intel) - see docs/DAY5_MAC_INSTRUCTOR_GUIDE.md.
