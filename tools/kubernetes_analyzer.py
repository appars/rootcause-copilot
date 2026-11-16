"""Static Kubernetes YAML analysis.

IMPORTANT
* This reads YAML text only. It does NOT connect to any cluster, so passing
  these checks does not prove the workload is healthy at runtime.
* Secret values are NEVER displayed, logged or stored: they are masked
  before anything leaves this module.
* yaml.safe_load_all is used - it cannot execute code embedded in YAML.
"""
from __future__ import annotations

import copy
from typing import Any

import yaml

MASK = "******** (masked)"
SUPPORTED_KINDS = ("Deployment", "Service", "ConfigMap", "Secret", "PersistentVolumeClaim")
STATIC_NOTE = ("Static YAML checks only: no live cluster was inspected, so runtime health "
               "(pods, events, actual resource usage) is not verified.")


class YamlParseError(ValueError):
    pass


def parse_yaml_documents(text: str) -> list[dict[str, Any]]:
    if not text or not text.strip():
        raise YamlParseError("No YAML content was provided.")
    try:
        docs = [d for d in yaml.safe_load_all(text) if d is not None]
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" (line {mark.line + 1}, column {mark.column + 1})" if mark else ""
        raise YamlParseError(f"Invalid YAML{where}: {getattr(exc, 'problem', exc)}") from exc
    if not docs:
        raise YamlParseError("The YAML contained no resources.")
    return docs


def mask_secrets(doc: Any) -> Any:
    """Return a copy where every Secret data/stringData value is replaced by a mask."""
    if not isinstance(doc, dict) or doc.get("kind") != "Secret":
        return doc
    masked = copy.deepcopy(doc)
    for key in ("data", "stringData"):
        if isinstance(masked.get(key), dict):
            masked[key] = {k: MASK for k in masked[key]}
    return masked


def masked_yaml(docs: list[Any]) -> str:
    return yaml.safe_dump_all([mask_secrets(d) for d in docs], sort_keys=False)


def _name(doc: dict[str, Any]) -> str:
    return str((doc.get("metadata") or {}).get("name") or "<unnamed>")


# Recommended correction per check id (deterministic - not LLM output).
RECOMMENDATIONS = {
    "structure": "Add apiVersion, kind and metadata.name to every document.",
    "unsupported-kind": "No action needed for this workshop tool.",
    "empty-configmap": "Add the required keys under data:, or remove the unused ConfigMap.",
    "secret-in-yaml": "Remove the Secret from the file and create it with kubectl or a secret manager.",
    "pvc-access-modes": "Add accessModes: [ReadWriteOnce].",
    "pvc-size": "Add resources.requests.storage, e.g. 1Gi.",
    "replicas": "Set spec.replicas explicitly (e.g. 1 for single-writer apps such as SQLite).",
    "invalid-replicas": "Use a non-negative integer, e.g. replicas: 1.",
    "selector": "Add spec.selector.matchLabels equal to the pod template labels.",
    "selector-labels": "Make spec.selector.matchLabels identical to spec.template.metadata.labels.",
    "pvc-reference": "Create the PersistentVolumeClaim (or fix claimName).",
    "containers": "Add at least one container with name and image.",
    "image": "Set image to a registry path with a version tag, e.g. user/app:1.2.0.",
    "image-tag": "Pin an immutable version tag instead of latest.",
    "resources-requests": "Add resources.requests (cpu, memory).",
    "resources-limits": "Add resources.limits (cpu, memory) sized from observed usage.",
    "limits-below-requests": "Make every limit greater than or equal to its request.",
    "readiness-probe": "Add a readinessProbe (e.g. httpGet on the health endpoint).",
    "liveness-probe": "Add a livenessProbe so a hung process is restarted.",
    "probe-port": "Point the probe at a port the container actually exposes.",
    "configmap-reference": "Create the ConfigMap or correct its name in the Deployment.",
    "secret-reference": "Create the Secret (outside Git) or correct its name.",
    "volume-mount": "Add a matching entry under spec.template.spec.volumes, or fix the mount name.",
    "unused-volume": "Mount the volume or remove it.",
    "rwo-multi-replica": "Use replicas: 1 with a ReadWriteOnce volume, or move state to a shared database.",
    "service-selector": "Make the Service selector match the pod template labels.",
    "target-port": "Set targetPort to a containerPort (number or name) of the selected pods.",
}


def _finding(severity: str, resource: str, check: str, message: str, explanation: str,
             evidence: str = "") -> dict[str, str]:
    return {"severity": severity, "resource": resource, "check": check, "message": message,
            "explanation": explanation, "evidence": evidence or "-",
            "recommendation": RECOMMENDATIONS.get(check, "Review this setting."),
            "source": "deterministic validation"}


_MEM_UNITS = {"Ki": 2**10, "Mi": 2**20, "Gi": 2**30, "Ti": 2**40, "K": 10**3, "M": 10**6, "G": 10**9, "T": 10**12}


def parse_quantity(value: Any, kind: str) -> float | None:
    """Parse Kubernetes CPU ('500m', '1') or memory ('512Mi', '1G') quantities. None if not parseable."""
    text = str(value).strip()
    try:
        if kind == "cpu":
            return float(text[:-1]) / 1000 if text.endswith("m") else float(text)
        for unit, factor in _MEM_UNITS.items():
            if text.endswith(unit):
                return float(text[: -len(unit)]) * factor
        return float(text)
    except ValueError:
        return None


def _pod_spec(dep: dict[str, Any]) -> dict[str, Any]:
    return (((dep.get("spec") or {}).get("template") or {}).get("spec") or {})


def analyze_kubernetes_yaml(text: str) -> dict[str, Any]:
    """Parse and check Kubernetes YAML. Returns findings + masked YAML. Raises YamlParseError."""
    docs = parse_yaml_documents(text)
    findings: list[dict[str, str]] = []
    resources: list[dict[str, Any]] = []

    by_kind: dict[str, list[dict[str, Any]]] = {}
    for d in docs:
        if not isinstance(d, dict) or "kind" not in d:
            findings.append(_finding("warning", "<unknown>", "structure",
                                     "A YAML document has no 'kind' field.",
                                     "Every Kubernetes object needs apiVersion, kind and metadata."))
            continue
        by_kind.setdefault(str(d["kind"]), []).append(d)
        summary: dict[str, Any] = {"kind": d["kind"], "name": _name(d),
                                   "namespace": (d.get("metadata") or {}).get("namespace", "(default)")}
        if d["kind"] == "Secret":
            keys = list((d.get("data") or {}).keys()) + list((d.get("stringData") or {}).keys())
            summary["keys"] = keys
            summary["values"] = "masked"
        resources.append(summary)

    configmaps = {_name(c) for c in by_kind.get("ConfigMap", [])}
    secrets = {_name(s) for s in by_kind.get("Secret", [])}
    pvcs = {_name(p) for p in by_kind.get("PersistentVolumeClaim", [])}
    rwo_pvcs = {_name(p) for p in by_kind.get("PersistentVolumeClaim", [])
                if "ReadWriteOnce" in ((p.get("spec") or {}).get("accessModes") or [])}

    for kind, items in by_kind.items():
        if kind not in SUPPORTED_KINDS:
            for d in items:
                findings.append(_finding("info", f"{kind}/{_name(d)}", "unsupported-kind",
                                         f"{kind} is not analysed by this workshop tool.",
                                         "Only Deployment, Service, ConfigMap, Secret and PVC are checked."))

    deployments = by_kind.get("Deployment", [])
    for dep in deployments:
        findings += _check_deployment(dep, configmaps, secrets, pvcs, rwo_pvcs)
    for svc in by_kind.get("Service", []):
        findings += _check_service(svc, deployments)
    for cm in by_kind.get("ConfigMap", []):
        if not cm.get("data") and not cm.get("binaryData"):
            findings.append(_finding("info", f"ConfigMap/{_name(cm)}", "empty-configmap", "ConfigMap has no data.",
                                     "An empty ConfigMap is valid but usually a mistake."))
    for sec in by_kind.get("Secret", []):
        if sec.get("stringData"):
            findings.append(_finding("warning", f"Secret/{_name(sec)}", "secret-in-yaml",
                                     "Secret uses stringData (plain-text values in the file). Values masked here.",
                                     "Never commit Secret values to Git - create Secrets with kubectl or a secret manager."))
        elif sec.get("data"):
            findings.append(_finding("warning", f"Secret/{_name(sec)}", "secret-in-yaml",
                                     "Secret contains base64 data. Values masked here.",
                                     "base64 is encoding, not encryption. Do not commit populated Secrets to Git."))
    for pvc in by_kind.get("PersistentVolumeClaim", []):
        spec = pvc.get("spec") or {}
        storage = ((spec.get("resources") or {}).get("requests") or {}).get("storage")
        if not spec.get("accessModes"):
            findings.append(_finding("warning", f"PersistentVolumeClaim/{_name(pvc)}", "pvc-access-modes",
                                     "PVC has no accessModes.", "Specify e.g. ReadWriteOnce."))
        if not storage:
            findings.append(_finding("error", f"PersistentVolumeClaim/{_name(pvc)}", "pvc-size",
                                     "PVC has no storage request.", "spec.resources.requests.storage is required."))

    order = {"error": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: order.get(f["severity"], 3))
    return {
        "resources": resources,
        "findings": findings,
        "counts": {s: sum(1 for f in findings if f["severity"] == s) for s in ("error", "warning", "info")},
        "masked_yaml": masked_yaml(docs),
        "note": STATIC_NOTE,
    }


def _check_deployment(dep: dict[str, Any], configmaps: set[str], secrets: set[str], pvcs: set[str],
                      rwo_pvcs: set[str] | None = None) -> list[dict[str, str]]:
    rwo_pvcs = rwo_pvcs or set()
    res = f"Deployment/{_name(dep)}"
    out: list[dict[str, str]] = []
    spec = dep.get("spec") or {}
    pod = _pod_spec(dep)
    template_labels = ((spec.get("template") or {}).get("metadata") or {}).get("labels") or {}
    match_labels = (spec.get("selector") or {}).get("matchLabels") or {}

    replicas = spec.get("replicas")
    if replicas is None:
        out.append(_finding("info", res, "replicas", "replicas not set (Kubernetes defaults to 1).",
                            "Set replicas explicitly so the desired state is obvious in Git.", "spec.replicas: (absent)"))
    elif isinstance(replicas, bool) or not isinstance(replicas, int) or replicas < 0:
        out.append(_finding("error", res, "invalid-replicas", f"replicas has an invalid value: {replicas!r}.",
                            "replicas must be a non-negative integer.", f"spec.replicas: {replicas!r}"))
    elif replicas == 0:
        out.append(_finding("warning", res, "replicas", "replicas is 0 - no pods will run.",
                            "A Deployment scaled to zero serves no traffic.", "spec.replicas: 0"))

    if not match_labels:
        out.append(_finding("error", res, "selector", "spec.selector.matchLabels is missing.",
                            "apps/v1 Deployments require a selector that matches the pod template labels."))
    elif any(template_labels.get(k) != v for k, v in match_labels.items()):
        out.append(_finding("error", res, "selector-labels", f"selector {match_labels} does not match pod labels {template_labels}.",
                            "Kubernetes rejects a Deployment whose selector does not match its template labels.",
                            f"selector.matchLabels={match_labels}; template.labels={template_labels}"))

    volumes = {v.get("name"): v for v in (pod.get("volumes") or []) if isinstance(v, dict)}
    for vname, vol in volumes.items():
        if "configMap" in vol and (vol["configMap"] or {}).get("name") not in configmaps:
            out.append(_ref_finding(res, "ConfigMap", (vol["configMap"] or {}).get("name"), vol["configMap"]))
        if "secret" in vol and (vol["secret"] or {}).get("secretName") not in secrets:
            out.append(_ref_finding(res, "Secret", (vol["secret"] or {}).get("secretName"), vol["secret"]))
        if "persistentVolumeClaim" in vol and (vol["persistentVolumeClaim"] or {}).get("claimName") not in pvcs:
            out.append(_finding("warning", res, "pvc-reference",
                                f"Volume '{vname}' uses PVC '{(vol['persistentVolumeClaim'] or {}).get('claimName')}' which is not in this YAML.",
                                "The pod stays Pending until the claim exists and is bound.",
                                f"volumes[{vname}].persistentVolumeClaim.claimName"))
    rwo_claims = [n for n, v in volumes.items() if "persistentVolumeClaim" in v
                  and (v["persistentVolumeClaim"] or {}).get("claimName") in rwo_pvcs]
    if isinstance(replicas, int) and not isinstance(replicas, bool) and replicas > 1 and rwo_claims:
        out.append(_finding("warning", res, "rwo-multi-replica",
                            f"replicas={replicas} but the pod mounts ReadWriteOnce volume(s) {rwo_claims}.",
                            "A ReadWriteOnce volume attaches to one node; extra replicas may stay Pending, and a "
                            "single-writer database (e.g. SQLite) must not be shared by several pods.",
                            f"spec.replicas: {replicas}; volumes: {rwo_claims}"))

    containers = [c for c in (pod.get("containers") or []) if isinstance(c, dict)]
    if not containers:
        out.append(_finding("error", res, "containers", "No containers defined.", "A pod needs at least one container."))
    for c in containers:
        cname = c.get("name", "<container>")
        where = f"{res} (container {cname})"
        image = str(c.get("image") or "").strip()
        if not image:
            out.append(_finding("error", where, "image", "Container image is missing or empty.",
                                "Kubernetes cannot start a container without an image.", "image: (empty)"))
        elif image.endswith(":latest") or ":" not in image.split("/")[-1]:
            out.append(_finding("warning", where, "image-tag", f"Image '{image}' uses 'latest' or no tag.",
                                "Use an immutable version tag (e.g. day4-v1) so GitOps rollouts and rollbacks are predictable.",
                                f"image: {image}"))
        resources = c.get("resources") or {}
        if not resources.get("requests"):
            out.append(_finding("warning", where, "resources-requests", "No resource requests.",
                                "Requests tell the scheduler how much CPU/memory the pod needs."))
        if not resources.get("limits"):
            out.append(_finding("warning", where, "resources-limits", "No resource limits.",
                                "Without limits one pod can starve others; with too-low memory limits pods get OOMKilled."))
        for kind in ("cpu", "memory"):
            req = (resources.get("requests") or {}).get(kind)
            lim = (resources.get("limits") or {}).get(kind)
            rq, lq = parse_quantity(req, kind), parse_quantity(lim, kind)
            if rq is not None and lq is not None and lq < rq:
                out.append(_finding("error", where, "limits-below-requests",
                                    f"{kind} limit {lim} is lower than its request {req}.",
                                    "Kubernetes rejects a container whose limit is below its request.",
                                    f"requests.{kind}: {req}; limits.{kind}: {lim}"))
        port_ids: set[Any] = set()
        for p in c.get("ports") or []:
            port_ids.add(p.get("containerPort"))
            if p.get("name"):
                port_ids.add(p.get("name"))
        for probe_name in ("readinessProbe", "livenessProbe", "startupProbe"):
            probe = c.get(probe_name) or {}
            handler = probe.get("httpGet") or probe.get("tcpSocket") or {}
            if port_ids and handler.get("port") is not None and handler.get("port") not in port_ids:
                out.append(_finding("error", where, "probe-port",
                                    f"{probe_name} uses port {handler.get('port')!r}, which the container does not expose.",
                                    "The probe always fails, so the pod never becomes ready or keeps restarting.",
                                    f"{probe_name}.port: {handler.get('port')!r}; ports: {sorted(map(str, port_ids))}"))
        if not c.get("readinessProbe"):
            out.append(_finding("warning", where, "readiness-probe", "No readinessProbe.",
                                "Without it, traffic may reach the pod before it is ready."))
        if not c.get("livenessProbe"):
            out.append(_finding("warning", where, "liveness-probe", "No livenessProbe.",
                                "Without it, a hung process is never restarted."))
        for ef in c.get("envFrom") or []:
            if "configMapRef" in ef and (ef["configMapRef"] or {}).get("name") not in configmaps:
                out.append(_ref_finding(where, "ConfigMap", (ef["configMapRef"] or {}).get("name"), ef["configMapRef"]))
            if "secretRef" in ef and (ef["secretRef"] or {}).get("name") not in secrets:
                out.append(_ref_finding(where, "Secret", (ef["secretRef"] or {}).get("name"), ef["secretRef"]))
        for env in c.get("env") or []:
            vf = (env or {}).get("valueFrom") or {}
            if "configMapKeyRef" in vf and (vf["configMapKeyRef"] or {}).get("name") not in configmaps:
                out.append(_ref_finding(where, "ConfigMap", (vf["configMapKeyRef"] or {}).get("name"), vf["configMapKeyRef"]))
            if "secretKeyRef" in vf and (vf["secretKeyRef"] or {}).get("name") not in secrets:
                out.append(_ref_finding(where, "Secret", (vf["secretKeyRef"] or {}).get("name"), vf["secretKeyRef"]))
        for vm in c.get("volumeMounts") or []:
            if vm.get("name") not in volumes:
                out.append(_finding("error", where, "volume-mount",
                                    f"volumeMount '{vm.get('name')}' has no matching volume.",
                                    "Every volumeMount name must match a volume in spec.template.spec.volumes.",
                                    f"volumeMounts[{vm.get('name')}] -> volumes: {sorted(map(str, volumes))}"))
    mounted = {vm.get("name") for c in containers for vm in (c.get("volumeMounts") or [])}
    for vname in volumes:
        if vname not in mounted:
            out.append(_finding("info", res, "unused-volume", f"Volume '{vname}' is defined but never mounted.",
                                "Unused volumes are harmless but usually a leftover or a typo.", f"volumes[{vname}]"))
    return out


def _ref_finding(resource: str, kind: str, name: Any, ref: dict[str, Any] | None) -> dict[str, str]:
    optional = bool((ref or {}).get("optional"))
    return _finding(
        "info" if optional else "warning", resource, f"{kind.lower()}-reference",
        f"References {kind} '{name}' which is not defined in the uploaded YAML" + (" (marked optional)." if optional else "."),
        f"If the {kind} does not exist in the cluster, the pod fails with CreateContainerConfigError. "
        "It may exist in the cluster already - this static check cannot see the cluster.",
        f"{kind} reference name: {name}" + (" (optional: true)" if optional else ""),
    )


def _check_service(svc: dict[str, Any], deployments: list[dict[str, Any]]) -> list[dict[str, str]]:
    res = f"Service/{_name(svc)}"
    out: list[dict[str, str]] = []
    spec = svc.get("spec") or {}
    selector = spec.get("selector") or {}
    if not selector:
        return [_finding("warning", res, "service-selector", "Service has no selector.",
                         "Without a selector the Service sends traffic nowhere (unless Endpoints are managed manually).")]
    matching = []
    for dep in deployments:
        labels = ((dep.get("spec") or {}).get("template") or {}).get("metadata", {}).get("labels") or {}
        if all(labels.get(k) == v for k, v in selector.items()):
            matching.append(dep)
    if deployments and not matching:
        out.append(_finding("error", res, "service-selector",
                            f"Selector {selector} matches no Deployment pod labels in this YAML.",
                            "The Service will have no endpoints, so requests fail.", f"spec.selector: {selector}"))
    for dep in matching:
        ports: set[Any] = set()
        for c in _pod_spec(dep).get("containers") or []:
            for p in c.get("ports") or []:
                ports.add(p.get("containerPort"))
                if p.get("name"):
                    ports.add(p.get("name"))
        for sp in spec.get("ports") or []:
            target = sp.get("targetPort", sp.get("port"))
            if ports and target not in ports:
                out.append(_finding("error", res, "target-port",
                                    f"targetPort {target} is not a containerPort of Deployment/{_name(dep)} ({sorted(map(str, ports))}).",
                                    "Traffic is forwarded to a port nothing listens on.", f"targetPort: {target!r}"))
    return out


def summarize_findings(result: dict[str, Any]) -> str:
    c = result["counts"]
    return f"{len(result['resources'])} resources: {c['error']} errors, {c['warning']} warnings, {c['info']} info."
