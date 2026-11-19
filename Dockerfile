# RootCause Copilot v1.1 - container image (workshop-simple, production-conscious)
# No API key, .env file or database is ever baked into the image: supply GROQ_API_KEY at run time
# (docker run -e / Kubernetes Secret) or paste it in the app's sidebar.
#
#   Build:  docker build -t DOCKERHUB_USERNAME/rootcause-copilot:latest .
#   Run:    docker run -d --name rootcause -p 8501:8501 -v rootcause-data:/data DOCKERHUB_USERNAME/rootcause-copilot:latest
#   Guides: README_WINDOWS.md, README_MAC.md, docs/DOCKER_DEPLOYMENT.md
#
# PYTHON_IMAGE can point to a mirror of the same official image (e.g. a company registry); keep the default otherwise.
ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE}

# Build label shown in the sidebar ("build ..."). Kubernetes overrides it with ROOTCAUSE_APP_VERSION.
ARG APP_VERSION=latest
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ROOTCAUSE_APP_VERSION=${APP_VERSION} \
    ROOTCAUSE_DATA_DIR=/data \
    HOME=/tmp

WORKDIR /app

# Non-root user that owns only the data directory.
RUN groupadd --gid 10001 app \
 && useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app \
 && mkdir -p /data && chown app:app /data

# Dependencies first: this layer is cached until requirements.txt changes.
COPY requirements.txt .
RUN python -m pip install -r requirements.txt

# Application code (see .dockerignore: no .env, no tests, no local database).
COPY . .

USER 10001
EXPOSE 8501
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://localhost:8501/_stcore/health', timeout=4).status == 200 else 1)"

CMD ["python", "-m", "streamlit", "run", "app.py", \
     "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
