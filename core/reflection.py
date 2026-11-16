"""Self-reflection / reviewer stage (Concept 5).

The deterministic checks below run in BOTH modes; in Live AI Mode an LLM
reviewer adds its own findings on top. At most two review rounds are
allowed. Reflection reduces mistakes - it does NOT guarantee correctness.
"""
from __future__ import annotations

import re
from typing import Any

from core.agent import CATEGORY_ACTIONS, CATEGORY_PATTERNS, category_support
from core.tool_executor import InvestigationState

# Claims a hypothesis might make, and the log evidence needed to back them up.
CLAIM_EVIDENCE: dict[str, tuple[re.Pattern[str], re.Pattern[str]]] = {
    "deployment/release": (re.compile(r"\b(deploy(?:ment|ed)?|release|rollout|new version)\b", re.I),
                           re.compile(r"deploy|rollout|release|version \d|image .*:", re.I)),
    "network/DNS": (re.compile(r"\b(network|dns|packet loss)\b", re.I),
                    re.compile(r"dns|unknownhost|network unreachable|connection reset", re.I)),
    "disk": (re.compile(r"\bdisk (?:full|space)\b", re.I), re.compile(r"no space left|disk", re.I)),
    "certificate/TLS": (re.compile(r"\b(certificate|tls|ssl)\b", re.I), re.compile(r"certificate|x509|ssl|tls", re.I)),
}
_LINE_REF = re.compile(r"\bL(\d+)\b")
_NEGATION = re.compile(r"\b(no|not|without|ruled out|unlikely)\b", re.I)


def deterministic_review(state: InvestigationState, diagnosis: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    issues: list[str] = []
    missing: list[str] = []
    alternatives: list[str] = []
    category = diagnosis.get("root_cause_category", "unknown")
    support = category_support(state)
    log_text = state.log_text or ""

    # 1. Does the hypothesis match the log evidence?
    if not state.log_analysis:
        checks.append({"check": "Evidence available", "passed": False, "detail": "No log evidence was analysed."})
        missing.append("Logs covering the incident window")
    elif category == "unknown":
        checks.append({"check": "Hypothesis matches logs", "passed": True,
                       "detail": "Hypothesis states that evidence is insufficient."})
    else:
        own = support.get(category, 0)
        ok = own > 0
        checks.append({"check": "Hypothesis matches logs", "passed": ok,
                       "detail": f"{own} log line(s) show patterns for '{category}'."})
        if not ok:
            issues.append(f"No detected log pattern supports the category '{category}'.")

    # 2. Cited line numbers must exist.
    total = state.log_analysis["total_lines"] if state.log_analysis else 0
    max_line = len(log_text.splitlines())
    bad_refs = sorted({int(n) for e in diagnosis.get("supporting_evidence", []) for n in _LINE_REF.findall(e)
                       if int(n) > max_line or int(n) < 1})
    checks.append({"check": "Cited evidence exists", "passed": not bad_refs,
                   "detail": "All cited log lines exist." if not bad_refs else f"Cites non-existent lines {bad_refs}."})
    if bad_refs:
        issues.append(f"Supporting evidence cites log lines that do not exist: {bad_refs}.")

    # 3. Unsupported claims (contradictions with the evidence actually present).
    # Sentences that negate a cause ("No deployment evidence was found") are not claims.
    sentences = re.split(r"(?<=[.!?])\s+", diagnosis.get("hypothesis", ""))
    asserted = " ".join(x for x in sentences if not _NEGATION.search(x))
    unsupported = [claim for claim, (in_hyp, in_logs) in CLAIM_EVIDENCE.items()
                   if in_hyp.search(asserted) and not in_logs.search(log_text)]
    checks.append({"check": "No unsupported claims", "passed": not unsupported,
                   "detail": "No unsupported claims found." if not unsupported else
                   f"Mentions {', '.join(unsupported)} but the logs contain no such evidence."})
    for claim in unsupported:
        issues.append(f"The hypothesis mentions a {claim} cause, but no {claim} evidence was found in the logs.")

    # 4. Plausible alternatives (other categories with real support).
    own = support.get(category, 0)
    for cat, n in sorted(support.items(), key=lambda kv: kv[1], reverse=True):
        if cat != category and n > 0:
            alternatives.append(f"{cat.replace('_', ' ')} ({n} supporting log lines)")
            if n > own and category != "unknown":
                issues.append(f"'{cat}' has more supporting evidence ({n}) than the chosen category ({own}).")
    checks.append({"check": "Alternatives considered", "passed": True,
                   "detail": ", ".join(alternatives) if alternatives else "No competing pattern found."})

    # 5. Missing evidence that would strengthen the diagnosis.
    if category == "configuration_error" and not state.yaml_analysis:
        missing.append("Kubernetes YAML / ConfigMap for the failing Deployment")
    if not state.similar_incidents and "retrieve_similar_incidents" not in state.unavailable:
        missing.append("No similar past incident found in memory (this may be a new failure mode)")
    for tool, reason in state.unavailable.items():
        missing.append(f"{tool} was unavailable: {reason[:100]}")
    missing.append("Live metrics (latency, saturation, resource usage) are not available in this simulated environment")

    # 6. Is the remediation supported by the findings?
    action_type = (diagnosis.get("remediation") or {}).get("action_type", "")
    allowed = CATEGORY_ACTIONS.get(category, CATEGORY_ACTIONS["unknown"])
    rem_ok = action_type in allowed
    checks.append({"check": "Recommendation supported", "passed": rem_ok,
                   "detail": f"'{action_type}' {'fits' if rem_ok else 'does not fit'} a '{category}' diagnosis."})
    if not rem_ok:
        issues.append(f"Remediation '{action_type}' is not a typical response to '{category}'.")

    # 7. Is the confidence justified?
    conf = diagnosis.get("confidence", "low")
    suggested = conf
    if issues and conf == "high":
        suggested = "medium"
    if (not state.log_analysis or category == "unknown") and conf != "low":
        suggested = "low"
    if own < 3 and conf == "high":
        suggested = "low"
    justified = suggested == conf
    checks.append({"check": "Confidence justified", "passed": justified,
                   "detail": f"Stated '{conf}'" + ("" if justified else f"; evidence supports at most '{suggested}'.")})
    if not justified:
        issues.append(f"Confidence '{conf}' is higher than the evidence supports (suggest '{suggested}').")

    if not state.log_analysis or (category == "unknown" and total == 0):
        verdict = "insufficient"
    elif issues:
        verdict = "revise"
    else:
        verdict = "supported"
    return {"verdict": verdict, "issues": issues, "missing_evidence": missing, "alternatives": alternatives,
            "confidence_justified": justified, "suggested_confidence": suggested, "checks": checks}


def merge_reviews(rule_review: dict[str, Any], llm_review: dict[str, Any] | None) -> dict[str, Any]:
    if not llm_review:
        return rule_review | {"reviewers": ["deterministic checks"]}
    order = {"supported": 0, "revise": 1, "insufficient": 2}
    verdict = max(rule_review["verdict"], llm_review["verdict"], key=lambda v: order.get(v, 1))
    def uniq(xs: list[str]) -> list[str]:
        out: list[str] = []
        for x in xs:
            if x and x not in out:
                out.append(x)
        return out
    conf_rank = {"low": 0, "medium": 1, "high": 2}
    suggested = min(rule_review["suggested_confidence"], llm_review.get("suggested_confidence", "low"),
                    key=lambda c: conf_rank.get(c, 0))
    return {"verdict": verdict,
            "issues": uniq(rule_review["issues"] + [f"LLM reviewer: {i}" for i in llm_review["issues"]]),
            "missing_evidence": uniq(rule_review["missing_evidence"] + llm_review["missing_evidence"]),
            "alternatives": uniq(rule_review["alternatives"] + llm_review["alternatives"]),
            "confidence_justified": rule_review["confidence_justified"] and llm_review["confidence_justified"],
            "suggested_confidence": suggested, "checks": rule_review["checks"],
            "reviewers": ["deterministic checks", "LLM reviewer"]}


def apply_review_adjustments(diagnosis: dict[str, Any], review: dict[str, Any]) -> dict[str, Any]:
    """Make the final answer honest: cap confidence and attach limitations/alternatives."""
    rank = {"low": 0, "medium": 1, "high": 2}
    final = dict(diagnosis)
    if rank.get(review["suggested_confidence"], 0) < rank.get(final.get("confidence", "low"), 0):
        final["confidence"] = review["suggested_confidence"]
    final["alternatives"] = list(dict.fromkeys(final.get("alternatives", []) + review["alternatives"]))[:6]
    final["limitations"] = list(dict.fromkeys(final.get("missing_evidence", []) + review["missing_evidence"]))[:8]
    if review["verdict"] == "insufficient":
        final["confidence"] = "low"
        final["limitations"].insert(0, "Evidence is insufficient for a reliable diagnosis.")
    return final


def category_patterns_text(category: str) -> str:
    return ", ".join(sorted(CATEGORY_PATTERNS.get(category, set()))) or "none"


# ============================================================ evidence labels
EVIDENCE_LABELS = {
    "strong": "Strong supporting evidence",
    "partial": "Partial supporting evidence",
    "contradictory": "Contradictory evidence",
    "insufficient": "Insufficient evidence",
}
# Log lines that indicate a resource is HEALTHY - they contradict a hypothesis blaming that resource.
_HEALTHY = {
    "memory_pressure": re.compile(r"heap used=[1-4]?\d%", re.I),      # below 50 %
    "cpu_pressure": re.compile(r"cpu usage [1-4]?\d%", re.I),        # below 50 %
    "database_connection_pool": re.compile(r"database connections active=\d+ idle=[1-9]", re.I),
}


def assess_evidence(state: InvestigationState, diagnosis: dict[str, Any], review: dict[str, Any]) -> dict[str, Any]:
    """Label the evidence for the hypothesis in plain words (no arbitrary percentages)."""
    from tools.log_analyzer import PATTERN_LABELS  # local import keeps module dependencies simple

    category = diagnosis.get("root_cause_category", "unknown")
    support = category_support(state)
    own = support.get(category, 0)
    supporting: list[str] = []
    contradictory: list[str] = []

    if state.log_analysis:
        hits = {p["id"]: p for p in state.log_analysis["patterns"]}
        for pid in sorted(CATEGORY_PATTERNS.get(category, set())):
            if pid in hits:
                supporting.append(f"Logs: {PATTERN_LABELS[pid]} in {hits[pid]['count']} line(s), first at "
                                  f"L{hits[pid]['first_line']}")
    for s in state.similar_incidents:
        if set(s.get("matched_on", [])) and any(str(m).startswith("pattern:") for m in s["matched_on"]):
            supporting.append(f"Memory: similar past incident {s['id']} (similarity {s['score']}) - {s['title']}")
    for k in state.kb_results[:2]:
        supporting.append(f"Knowledge base: {k['filename']} (matched {', '.join(k['matched_terms'][:4])})")

    # Contradictions: claims the evidence does not show, competing causes with MORE support,
    # and log lines showing the blamed resource was healthy.
    conflicts = [i for i in review.get("issues", [])
                 if "but no" in i or "more supporting evidence" in i or "No detected log pattern supports" in i]
    contradictory.extend(conflicts)
    rx = _HEALTHY.get(category)
    if rx:
        for i, line in enumerate(state.log_text.splitlines(), 1):
            if rx.search(line):
                contradictory.append(f"Healthy reading at L{i}: {line.strip()[:160]}")
    contradictory = contradictory[:6]

    independent_sources = sum(1 for prefix in ("Logs:", "Memory:", "Knowledge base:")
                              if any(x.startswith(prefix) for x in supporting))
    if not state.log_analysis or category == "unknown" or review.get("verdict") == "insufficient":
        label = "insufficient"
    elif conflicts or (contradictory and own == 0):
        label = "contradictory"
    elif contradictory or review.get("verdict") != "supported":
        label = "partial"
    elif own >= 5 and independent_sources >= 2:
        label = "strong"
    elif own > 0:
        label = "partial"
    else:
        label = "insufficient"
    explanation = {
        "strong": "Several independent sources agree and the reviewer found no contradiction. Still a hypothesis.",
        "partial": "Some evidence supports the hypothesis, but there are gaps or open questions.",
        "contradictory": "Some evidence conflicts with the hypothesis - it should be revised or investigated further.",
        "insufficient": "There is not enough evidence to support a root-cause conclusion.",
    }[label]
    return {"label": label, "label_text": EVIDENCE_LABELS[label], "explanation": explanation,
            "supporting": supporting, "contradictory": contradictory,
            "missing": review.get("missing_evidence", [])}
