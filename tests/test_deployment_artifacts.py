"""Offline checks for the Dockerfile, Kubernetes manifests, ArgoCD Application and GitOps starter."""
import json
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
GITOPS = ROOT.parent / "rootcause-copilot-gitops"
K8S_DIRS = [ROOT / "kubernetes"] + ([GITOPS / "apps" / "rootcause-copilot"] if GITOPS.exists() else [])


def _docs(folder: Path) -> dict[str, dict]:
    out = {}
    for f in folder.glob("*.yaml"):
        for d in yaml.safe_load_all(f.read_text()):
            if d and d.get("kind") != "Kustomization":
                out[d["kind"]] = d
    return out


@pytest.mark.parametrize("folder", K8S_DIRS, ids=lambda p: p.parent.name + "/" + p.name)
def test_manifests_are_consistent(folder):
    docs = _docs(folder)
    assert {"Namespace", "ConfigMap", "PersistentVolumeClaim", "Deployment", "Service"} <= set(docs)
    assert "Secret" not in docs, "Secrets must never be committed"
    dep = docs["Deployment"]["spec"]
    assert dep["replicas"] == 1, "SQLite on one RWO volume -> exactly one replica"
    assert dep["strategy"]["type"] == "Recreate"
    pod = dep["template"]["spec"]
    c = pod["containers"][0]
    assert not c["image"].endswith(":latest")
    assert c["ports"][0]["containerPort"] == 8501
    for probe in ("startupProbe", "readinessProbe", "livenessProbe"):
        assert c[probe]["httpGet"]["path"] == "/_stcore/health"
    assert c["resources"]["requests"] and c["resources"]["limits"]
    assert pod["securityContext"]["runAsNonRoot"] is True
    secret_ref = c["env"][0]["valueFrom"]["secretKeyRef"]
    assert secret_ref["optional"] is True
    # data path: ConfigMap value == volume mount path, volume -> PVC
    assert docs["ConfigMap"]["data"]["ROOTCAUSE_DATA_DIR"] == c["volumeMounts"][0]["mountPath"] == "/data"
    assert pod["volumes"][0]["persistentVolumeClaim"]["claimName"] == docs["PersistentVolumeClaim"]["metadata"]["name"]
    svc = docs["Service"]["spec"]
    assert svc["selector"] == dep["template"]["metadata"]["labels"]
    assert svc["ports"][0]["targetPort"] == c["ports"][0]["name"]
    kust = yaml.safe_load((folder / "kustomization.yaml").read_text())
    assert all((folder / r).exists() for r in kust["resources"])
    assert kust["images"][0]["newTag"] != "latest"


def test_manifests_pass_our_own_analyzer():
    from tools.kubernetes_analyzer import analyze_kubernetes_yaml
    text = "\n---\n".join((ROOT / "kubernetes" / f).read_text() for f in
                          ("namespace.yaml", "configmap.yaml", "pvc.yaml", "deployment.yaml", "service.yaml"))
    r = analyze_kubernetes_yaml(text)
    assert r["counts"]["error"] == 0
    # only expected note: the optional Secret is created outside Git
    assert all(f["severity"] == "info" for f in r["findings"])


def test_argocd_application():
    for f in [ROOT / "argocd" / "rootcause-copilot-application.yaml"] + list((GITOPS / "argocd").glob("*.yaml")):
        app = yaml.safe_load(f.read_text())
        assert app["kind"] == "Application" and app["metadata"]["namespace"] == "argocd"
        assert app["spec"]["source"]["path"] == "apps/rootcause-copilot"
        assert app["spec"]["destination"]["namespace"] == "rootcause"
        assert "automated" not in app["spec"].get("syncPolicy", {}), "first sync must be manual"
    patch = json.loads((ROOT / "argocd" / "autosync-patch.json").read_text())
    assert patch["spec"]["syncPolicy"]["automated"]["selfHeal"] is True


def test_gitops_copy_matches_reference_manifests():
    if not GITOPS.exists():
        pytest.skip("GitOps starter folder not next to the app repository")
    for f in (ROOT / "kubernetes").glob("*.yaml"):
        assert (GITOPS / "apps" / "rootcause-copilot" / f.name).read_text() == f.read_text(), f.name


def test_dockerfile_is_safe():
    df = (ROOT / "Dockerfile").read_text()
    assert re.search(r"^FROM python:3\.\d+-slim", df, re.M)
    assert "USER 10001" in df and "EXPOSE 8501" in df and "--server.address=0.0.0.0" in df
    ignore = (ROOT / ".dockerignore").read_text().splitlines()
    for entry in (".env", "data_store", ".venv", "*.db"):
        assert entry in ignore
