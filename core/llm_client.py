"""Groq client wrapper with honest error classification and bounded retries.

Concept 6 - Error Recovery for the LLM dependency:
    * transient errors (timeouts, connection problems, 429 rate limits,
      5xx provider errors) are retried a small, bounded number of times with
      exponential backoff;
    * non-transient errors (invalid key, malformed request, unknown model)
      are NOT retried - retrying cannot fix them.

The API key lives only inside this object for the current Streamlit session.
It is never logged, printed, stored in SQLite or written to reports.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable

import config


class LLMError(Exception):
    """A classified LLM failure with a user-friendly message."""

    def __init__(self, kind: str, message: str, transient: bool = False):
        super().__init__(message)
        self.kind = kind
        self.transient = transient
        self.user_message = message


@dataclass
class ToolCallRequest:
    id: str
    name: str
    arguments_json: str


@dataclass
class ChatResult:
    content: str
    tool_calls: list[ToolCallRequest]


def classify_exception(exc: Exception) -> LLMError:
    """Map Groq SDK exceptions to LLMError. Works without importing groq (tests use fakes)."""
    if isinstance(exc, LLMError):
        return exc
    name = type(exc).__name__
    status = getattr(exc, "status_code", None)
    body = str(getattr(exc, "body", "") or exc)
    if name in ("AuthenticationError", "PermissionDeniedError") or status in (401, 403):
        return LLMError("auth", "The Groq API key was rejected (invalid, revoked or without access). "
                                "Check the key in Settings. This error is not retried.")
    if name == "RateLimitError" or status == 429:
        return LLMError("rate_limit", "Groq rate limit or quota reached (HTTP 429). Wait a minute, check your "
                                      "account limits, or switch to Demo Mode explicitly.", transient=True)
    if name == "APITimeoutError":
        return LLMError("timeout", "The Groq API did not respond in time.", transient=True)
    if name == "APIConnectionError":
        return LLMError("connection", "Could not reach the Groq API (network problem or firewall).", transient=True)
    if name == "InternalServerError" or (isinstance(status, int) and status >= 500):
        return LLMError("provider", f"Groq returned a temporary server error ({status}).", transient=True)
    if name == "NotFoundError" or status == 404:
        return LLMError("not_found", f"Model '{config.LLM_MODEL}' was not found for this key/account.")
    if "tool_use_failed" in body:
        return LLMError("tool_use_failed", "The model produced an invalid tool call.")
    if name == "BadRequestError" or status == 400:
        return LLMError("bad_request", "The request was rejected by Groq (HTTP 400). This is not retried.")
    return LLMError("unknown", f"Unexpected LLM error: {name}")


class GroqLLM:
    """Thin wrapper around the official Groq Python SDK for the fixed workshop model."""

    def __init__(self, api_key: str, *, client: Any | None = None,
                 on_retry: Callable[[str], None] | None = None,
                 sleep: Callable[[float], None] = time.sleep,
                 max_retries: int = config.LLM_MAX_RETRIES,
                 backoff: float = config.LLM_BACKOFF_SECONDS):
        if not api_key or not api_key.strip():
            raise LLMError("auth", "No Groq API key provided. Add your key in Settings or use Demo Mode.")
        if client is None:
            from groq import Groq
            # SDK-level retries disabled: we retry ourselves so recovery is visible in the timeline.
            client = Groq(api_key=api_key.strip(), timeout=config.LLM_TIMEOUT_SECONDS, max_retries=0)
        self._client = client
        self._on_retry = on_retry or (lambda msg: None)
        self._sleep = sleep
        self._max_retries = max_retries
        self._backoff = backoff
        self.calls_made = 0

    def set_retry_callback(self, cb: Callable[[str], None]) -> None:
        self._on_retry = cb

    def __repr__(self) -> str:  # never show the key
        return f"GroqLLM(model={config.LLM_MODEL!r}, key=****)"

    # ------------------------------------------------------------- internals
    def _with_retries(self, fn: Callable[[], Any]) -> Any:
        attempt = 0
        while True:
            try:
                self.calls_made += 1
                return fn()
            except Exception as exc:  # noqa: BLE001 - classified below
                err = classify_exception(exc)
                if not err.transient or attempt >= self._max_retries:
                    raise err from exc
                wait = self._backoff * (2 ** attempt)
                attempt += 1
                self._on_retry(f"{err.kind}: retry {attempt}/{self._max_retries} after {wait:.1f}s")
                self._sleep(wait)

    def _base_kwargs(self) -> dict[str, Any]:
        return {"model": config.LLM_MODEL, "temperature": 0.2,
                "max_completion_tokens": config.LLM_MAX_OUTPUT_TOKENS,
                "reasoning_effort": config.LLM_REASONING_EFFORT}

    # ------------------------------------------------------------------ API
    def test_connection(self) -> str:
        """Cheap check (no tokens generated): list the models this key can use and look for the fixed model.

        models.list() is used instead of models.retrieve(): the model id contains a slash
        ("openai/gpt-oss-20b"), and groq SDK 1.x URL-encodes it in the retrieve path
        (/models/openai%2Fgpt-oss-20b), which the API answers with 404 even for a valid key.
        """
        listing = self._with_retries(lambda: self._client.models.list())
        ids = {getattr(m, "id", None) for m in (getattr(listing, "data", None) or [])}
        if config.LLM_MODEL not in ids:
            raise LLMError("not_found", f"Model '{config.LLM_MODEL}' was not found for this key/account.")
        return f"Connected to {config.LLM_PROVIDER}; model '{config.LLM_MODEL}' is available."

    def chat_tools(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ChatResult:
        """One chat turn where the model may request ONE tool call (gpt-oss-20b has no parallel tool use)."""
        def call() -> Any:
            return self._client.chat.completions.create(
                messages=messages, tools=tools, tool_choice="auto", **self._base_kwargs())
        resp = self._with_retries(call)
        msg = resp.choices[0].message
        calls = [ToolCallRequest(tc.id, tc.function.name, tc.function.arguments or "{}")
                 for tc in (getattr(msg, "tool_calls", None) or [])]
        # NOTE: msg.reasoning (if any) is deliberately ignored - we never display hidden reasoning.
        return ChatResult(content=(msg.content or "").strip(), tool_calls=calls)

    def chat_json(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Ask for a JSON object (JSON mode) and validate that it parses; one corrective retry."""
        convo = list(messages)
        for attempt in range(2):
            def call() -> Any:
                return self._client.chat.completions.create(
                    messages=convo, response_format={"type": "json_object"}, **self._base_kwargs())
            resp = self._with_retries(call)
            content = (resp.choices[0].message.content or "").strip()
            try:
                data = json.loads(content)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                pass
            convo = convo + [{"role": "assistant", "content": content[:2000]},
                             {"role": "user", "content": "That was not a valid JSON object. Reply with ONLY the JSON object."}]
        raise LLMError("invalid_output", "The model did not return valid JSON after a corrective retry.")


def run_capability_check(llm: GroqLLM) -> dict[str, Any]:
    """Explicit compatibility test for the fixed model: connection, tool calling, JSON mode."""
    report: dict[str, Any] = {"model": config.LLM_MODEL}
    try:
        report["connection"] = {"ok": True, "detail": llm.test_connection()}
    except LLMError as e:
        report["connection"] = {"ok": False, "detail": e.user_message}
        return report
    ping_tool = [{"type": "function", "function": {
        "name": "ping_tool", "description": "Returns pong. Call this tool exactly once.",
        "parameters": {"type": "object", "properties": {"word": {"type": "string"}}, "required": ["word"]}}}]
    try:
        res = llm.chat_tools([{"role": "user", "content": "Call ping_tool with word='hello'."}], ping_tool)
        ok = any(c.name == "ping_tool" for c in res.tool_calls)
        report["tool_calling"] = {"ok": ok, "detail": "tool call returned" if ok else "model answered without a tool call"}
    except LLMError as e:
        report["tool_calling"] = {"ok": False, "detail": e.user_message}
    try:
        data = llm.chat_json([{"role": "user", "content": 'Return the JSON object {"status": "ok"}.'}])
        report["json_mode"] = {"ok": data.get("status") == "ok", "detail": json.dumps(data)[:120]}
    except LLMError as e:
        report["json_mode"] = {"ok": False, "detail": e.user_message}
    return report
