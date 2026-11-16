import pytest

import config
from tools.kubernetes_analyzer import MASK, YamlParseError, analyze_kubernetes_yaml


def _yaml(name):
    return (config.SAMPLE_K8S_DIR / name).read_text(encoding="utf-8")


def test_parses_supported_resources():
    r = analyze_kubernetes_yaml(_yaml("payment_service_example.yaml"))
    kinds = {x["kind"] for x in r["resources"]}
    assert kinds == {"Deployment", "ConfigMap", "Secret", "PersistentVolumeClaim", "Service"}
    assert r["counts"]["error"] == 0


def test_secret_values_are_masked_everywhere():
    for name, secret in (("payment_service_example.yaml", "ZmFrZS1kZW1vLXZhbHVlLW5vdC1yZWFs"),
                         ("common_mistakes.yaml", "this-is-a-fake-demo-key")):
        r = analyze_kubernetes_yaml(_yaml(name))
        assert secret not in r["masked_yaml"]
        assert MASK in r["masked_yaml"]
        assert secret not in str(r["findings"]) and secret not in str(r["resources"])


def test_detects_common_mistakes():
    checks = {f["check"] for f in analyze_kubernetes_yaml(_yaml("common_mistakes.yaml"))["findings"]}
    assert {"selector-labels", "volume-mount", "service-selector", "pvc-size", "image-tag",
            "readiness-probe", "liveness-probe", "resources-limits", "secret-in-yaml"} <= checks


def test_missing_configmap_reference_for_inc004():
    r = analyze_kubernetes_yaml(_yaml("inc004_notification_service.yaml"))
    msgs = " ".join(f["message"] for f in r["findings"])
    assert "notification-config-v2" in msgs


def test_target_port_mismatch():
    text = """
apiVersion: apps/v1
kind: Deployment
metadata: {name: a}
spec:
  replicas: 1
  selector: {matchLabels: {app: a}}
  template:
    metadata: {labels: {app: a}}
    spec:
      containers: [{name: a, image: a:1, ports: [{containerPort: 9000}]}]
---
apiVersion: v1
kind: Service
metadata: {name: a}
spec:
  selector: {app: a}
  ports: [{port: 80, targetPort: 8080}]
"""
    assert "target-port" in {f["check"] for f in analyze_kubernetes_yaml(text)["findings"]}


def test_invalid_yaml_reports_location():
    with pytest.raises(YamlParseError, match="line"):
        analyze_kubernetes_yaml((config.SAMPLE_DATA_DIR / "error_samples" / "invalid_yaml.yaml").read_text())


def test_empty_yaml():
    with pytest.raises(YamlParseError):
        analyze_kubernetes_yaml("   ")


def test_unsafe_yaml_tags_are_not_executed():
    with pytest.raises(YamlParseError):
        analyze_kubernetes_yaml("!!python/object/apply:os.system ['echo hacked']")
