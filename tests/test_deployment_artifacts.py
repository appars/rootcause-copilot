"""Offline checks for the Dockerfile, .dockerignore, Kubernetes manifests, ArgoCD Application and CI workflows.

The real `kubectl kustomize` + kubeconform validation runs in GitHub Actions (.github/workflows/ci.yml).
These tests need no cluster and no Docker: they render the Kustomization the same simple way
(resources only - no generators or patches are used) and check every cross-reference.
"""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
K8S = ROOT / "kubernetes"
NAMESPACE = "rootcause"


def _render() -> list[dict]:
    """Equivalent of `kubectl kustomize kubernetes/` for this resources-only Kustomization."""
    kust = yaml.safe_load((K8S / "kustomization.yaml").read_text())
    assert set(kust) <= {"apiVersion", "kind", "resources"}, "update _render() if Kustomize features are added"
    docs = []
    for res in kust["resources"]:
        docs += [d for d in yaml.safe_load_all((K8S / res).read_text()) if d]
    return docs


def _by_kind() -> dict[str, dict]:
    return {d["kind"]: d for d in _render()}


def test_kustomization_lists_every_manifest_and_no_secret():
    kust = yaml.safe_load((K8S / "kustomization.yaml").read_text())
    assert all((K8S / r).exists() for r in kust["resources"])
    assert sorted(kust["resources"]) == sorted(p.name for p in K8S.glob("*.yaml") if p.name != "kustomization.yaml")
    kinds = [d["kind"] for d in _render()]
    assert sorted(kinds) == sorted(["Namespace", "ConfigMap", "PersistentVolumeClaim", "Deployment", "Service"])
    assert "Secret" not in kinds, "Secrets must never be committed"
    assert "groq-secret" not in (K8S / "kustomization.yaml").read_text()


def test_every_resource_is_in_the_same_namespace():
    for d in _render():
        if d["kind"] == "Namespace":
            assert d["metadata"]["name"] == NAMESPACE
        else:
            assert d["metadata"]["namespace"] == NAMESPACE, d["kind"]


def test_deployment_single_replica_sqlite_rules():
    dep = _by_kind()["Deployment"]["spec"]
    assert dep["replicas"] == 1, "SQLite on one ReadWriteOnce volume -> exactly one replica"
    assert dep["strategy"]["type"] == "Recreate", "old pod must release the volume before the new one starts"


def test_image_convention_latest_with_always_pull():
    c = _by_kind()["Deployment"]["spec"]["template"]["spec"]["containers"][0]
    # either the placeholder (course repo) or a real lowercase Docker Hub username (student fork)
    assert re.fullmatch(r"docker\.io/(DOCKERHUB_USERNAME|[a-z0-9]+)/rootcause-copilot:latest", c["image"]), c["image"]
    assert c["imagePullPolicy"] == "Always", "a moving :latest tag must be pulled again on every pod start"


def test_probes_ports_resources_and_security():
    pod = _by_kind()["Deployment"]["spec"]["template"]["spec"]
    c = pod["containers"][0]
    assert c["ports"][0] == {"name": "http", "containerPort": 8501}
    for probe in ("startupProbe", "readinessProbe", "livenessProbe"):
        assert c[probe]["httpGet"] == {"path": "/_stcore/health", "port": "http"}
    assert c["resources"]["requests"] and c["resources"]["limits"]
    assert pod["securityContext"]["runAsNonRoot"] is True and pod["securityContext"]["runAsUser"] == 10001
    assert pod["securityContext"]["fsGroup"] == 10001, "makes the PVC writable for the non-root user"
    assert pod["automountServiceAccountToken"] is False
    assert c["securityContext"]["allowPrivilegeEscalation"] is False
    assert c["securityContext"]["capabilities"]["drop"] == ["ALL"]
    assert not c["securityContext"].get("privileged", False)


def test_cross_references_resolve():
    k = _by_kind()
    pod = k["Deployment"]["spec"]["template"]["spec"]
    c = pod["containers"][0]
    # ConfigMap
    assert c["envFrom"][0]["configMapRef"]["name"] == k["ConfigMap"]["metadata"]["name"]
    # data directory: ConfigMap value == mount path, volume -> PVC
    assert k["ConfigMap"]["data"]["ROOTCAUSE_DATA_DIR"] == c["volumeMounts"][0]["mountPath"] == "/data"
    assert pod["volumes"][0]["persistentVolumeClaim"]["claimName"] == k["PersistentVolumeClaim"]["metadata"]["name"]
    # optional Secret: same name/key as the template and the documented kubectl command
    env = {e["name"]: e for e in c["env"]}
    ref = env["GROQ_API_KEY"]["valueFrom"]["secretKeyRef"]
    tpl = yaml.safe_load((K8S / "groq-secret.template").read_text())
    assert ref["optional"] is True
    assert (ref["name"], ref["key"]) == (tpl["metadata"]["name"], "GROQ_API_KEY")
    assert tpl["stringData"]["GROQ_API_KEY"] == "REPLACE_WITH_YOUR_GROQ_API_KEY"
    # release label used by the GitOps demo
    assert env["ROOTCAUSE_APP_VERSION"]["value"]
    # Service -> pods
    svc = k["Service"]["spec"]
    assert svc["selector"] == k["Deployment"]["spec"]["template"]["metadata"]["labels"]
    assert svc["ports"][0]["targetPort"] == c["ports"][0]["name"]


def test_storage_and_namespace_protected_from_argocd_deletion():
    k = _by_kind()
    for kind in ("PersistentVolumeClaim", "Namespace"):
        opts = k[kind]["metadata"]["annotations"]["argocd.argoproj.io/sync-options"]
        assert "Prune=false" in opts and "Delete=false" in opts, kind


def test_manifests_pass_our_own_analyzer():
    from tools.kubernetes_analyzer import analyze_kubernetes_yaml
    text = "\n---\n".join(yaml.safe_dump(d) for d in _render())
    r = analyze_kubernetes_yaml(text)
    assert r["counts"]["error"] == 0
    assert all(f["severity"] in ("info", "warning") for f in r["findings"])


def test_argocd_application_watches_this_repository():
    app = yaml.safe_load((ROOT / "argocd" / "rootcause-copilot-application.yaml").read_text())
    assert app["kind"] == "Application" and app["metadata"]["namespace"] == "argocd"
    src = app["spec"]["source"]
    assert re.fullmatch(r"https://github\.com/[^/]+/rootcause-copilot(\.git)?", src["repoURL"]), "same repo, no -gitops repo"
    assert src["path"] == "kubernetes" and src["targetRevision"] == "main"
    assert app["spec"]["destination"] == {"server": "https://kubernetes.default.svc", "namespace": NAMESPACE}
    auto = app["spec"]["syncPolicy"]["automated"]
    assert auto["selfHeal"] is True and auto["prune"] is False, "conservative pruning"
    assert "CreateNamespace=true" in app["spec"]["syncPolicy"]["syncOptions"]


def test_dockerfile_is_safe():
    df = (ROOT / "Dockerfile").read_text()
    assert re.search(r"^ARG PYTHON_IMAGE=python:3\.1[1-3]-slim$", df, re.M)
    assert re.search(r"^FROM \$\{PYTHON_IMAGE\}$", df, re.M)
    assert "USER 10001" in df and "EXPOSE 8501" in df and "--server.address=0.0.0.0" in df
    assert "HEALTHCHECK" in df and "/_stcore/health" in df
    assert "ROOTCAUSE_DATA_DIR=/data" in df and "chown app:app /data" in df
    assert not re.search(r"GROQ_API_KEY\s*=", df), "never bake the key into the image"
    assert "COPY .env" not in df


def test_dockerignore_excludes_secrets_state_and_dev_files():
    ignore = (ROOT / ".dockerignore").read_text().splitlines()
    for entry in (".git", ".env", ".env.*", ".venv", "venv", "**/__pycache__", "**/*.pyc", "data_store", "*.db",
                  "*.sqlite", "tests", ".github", "*.secret.yaml"):
        assert entry in ignore, entry
    # but never exclude what the app needs at run time
    for needed in ("app.py", "core", "memory", "tools", "ui", "data", ".streamlit", "requirements.txt", "config.py"):
        assert needed not in ignore, needed


def test_ci_workflows_are_safe():
    ci = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
    assert {"tests", "manifests", "docker"} <= set(ci["jobs"])
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "secrets." not in text, "ordinary CI must not need any secret"
    assert "docker push" not in text and "push: true" not in text, "CI must never publish images"
    pub = (ROOT / ".github" / "workflows" / "docker-publish.yml").read_text()
    on = yaml.safe_load(pub)[True]  # PyYAML parses the key 'on' as True
    assert list(on) == ["workflow_dispatch"], "publishing is manual only"
    assert "secrets.DOCKERHUB_TOKEN" in pub and "password: ${{ secrets.DOCKERHUB_TOKEN }}" in pub
