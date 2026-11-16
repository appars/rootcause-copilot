"""Controlled tool registry (Concept 3 - Dynamic Decision-Making, safely).

The model may only call tools in this allowlist, and every argument is
validated against an explicit schema BEFORE execution. Unknown tools or
invalid arguments are rejected and recorded, never executed.
"""
from __future__ import annotations

import json
from typing import Any

from tools.log_analyzer import PATTERN_LABELS


class ToolValidationError(ValueError):
    pass


_REASON = {"type": "string", "maxLength": 160,
           "description": "One short sentence explaining why this tool is needed now (shown to the engineer)."}

# name -> spec. "llm" = may the model select it? (report generation is orchestrator-only)
TOOL_SPECS: dict[str, dict[str, Any]] = {
    "analyze_logs": {
        "llm": True,
        "description": "Summarise the uploaded incident logs: counts, time range, exceptions and detected patterns. "
                       "Optionally focus on one pattern id.",
        "properties": {"focus_pattern": {"type": "string", "enum": sorted(PATTERN_LABELS)}, "reason": _REASON},
        "required": [],
    },
    "search_error_patterns": {
        "llm": True,
        "description": "Return log lines matching a known pattern id (e.g. db_pool_pressure) or a short keyword.",
        "properties": {"query": {"type": "string", "maxLength": 60}, "reason": _REASON},
        "required": ["query"],
    },
    "retrieve_similar_incidents": {
        "llm": True,
        "description": "Search persistent incident memory (SQLite) for similar past incidents and their resolutions.",
        "properties": {"query": {"type": "string", "maxLength": 200},
                       "top_k": {"type": "integer", "minimum": 1, "maximum": 5}, "reason": _REASON},
        "required": ["query"],
    },
    "search_knowledge_base": {
        "llm": True,
        "description": "Search runbooks and technical documents in the knowledge base.",
        "properties": {"query": {"type": "string", "maxLength": 200},
                       "top_k": {"type": "integer", "minimum": 1, "maximum": 5}, "reason": _REASON},
        "required": ["query"],
    },
    "analyze_kubernetes_yaml": {
        "llm": True,
        "description": "Run static checks on the Kubernetes YAML attached to this incident (if any). "
                       "Secret values are masked. Does not contact a cluster.",
        "properties": {"reason": _REASON},
        "required": [],
    },
    "generate_investigation_report": {
        "llm": False,
        "description": "Create the Markdown investigation report (run by the orchestrator at the end).",
        "properties": {},
        "required": [],
    },
}


def llm_tool_definitions() -> list[dict[str, Any]]:
    """OpenAI-compatible function definitions sent to Groq."""
    defs = []
    for name, spec in TOOL_SPECS.items():
        if not spec["llm"]:
            continue
        defs.append({"type": "function", "function": {
            "name": name, "description": spec["description"],
            "parameters": {"type": "object", "properties": spec["properties"], "required": spec["required"],
                           "additionalProperties": False}}})
    return defs


def parse_arguments(raw: str | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ToolValidationError(f"Arguments are not valid JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ToolValidationError("Arguments must be a JSON object.")
    return data


def validate_tool_call(name: str, args: dict[str, Any], llm_call: bool = True) -> tuple[dict[str, Any], str]:
    """Return (clean_args, reason). Raises ToolValidationError for anything not allowed."""
    if name not in TOOL_SPECS:
        raise ToolValidationError(f"Tool '{name}' is not in the allowlist.")
    spec = TOOL_SPECS[name]
    if llm_call and not spec["llm"]:
        raise ToolValidationError(f"Tool '{name}' cannot be selected by the model.")
    props = spec["properties"]
    unknown = set(args) - set(props)
    if unknown:
        raise ToolValidationError(f"Unexpected argument(s) for {name}: {sorted(unknown)}")
    for req in spec["required"]:
        if req not in args or args[req] in (None, ""):
            raise ToolValidationError(f"Missing required argument '{req}' for {name}.")
    clean: dict[str, Any] = {}
    for key, value in args.items():
        rule = props[key]
        if rule["type"] == "string":
            if not isinstance(value, str):
                raise ToolValidationError(f"'{key}' must be a string.")
            value = value.strip()
            if len(value) > rule.get("maxLength", 500):
                raise ToolValidationError(f"'{key}' is longer than {rule['maxLength']} characters.")
            if "enum" in rule and value not in rule["enum"]:
                raise ToolValidationError(f"'{key}' must be one of {rule['enum']}.")
        elif rule["type"] == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                if isinstance(value, str) and value.isdigit():
                    value = int(value)
                else:
                    raise ToolValidationError(f"'{key}' must be an integer.")
            if not rule.get("minimum", value) <= value <= rule.get("maximum", value):
                raise ToolValidationError(f"'{key}' must be between {rule['minimum']} and {rule['maximum']}.")
        clean[key] = value
    reason = str(clean.pop("reason", "") or "")
    return clean, reason
