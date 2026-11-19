"""Regression: "Connect / Test connection" must work with every supported groq SDK version.

groq SDK 1.x URL-encodes path parameters, so models.retrieve("openai/gpt-oss-20b") requests
/openai/v1/models/openai%2Fgpt-oss-20b, which Groq answers with 404 even for a valid key (seen in the Docker
image, which installs the newest SDK). The check therefore uses models.list(). The real SDK is driven through an
httpx MockTransport that behaves like the Groq API - no network and no key needed.
"""
import httpx
import pytest

import config
from core.llm_client import GroqLLM, LLMError


def _client(model_ids):
    import groq
    requested = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.raw_path.decode())
        if request.url.raw_path == b"/openai/v1/models":
            return httpx.Response(200, json={"object": "list", "data": [
                {"id": m, "object": "model", "created": 0, "owned_by": "test"} for m in model_ids]})
        return httpx.Response(404, json={"error": {"message": "model not found", "type": "invalid_request_error"}})

    client = groq.Groq(api_key="test-key-not-real", max_retries=0,
                       http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    return client, requested


def test_connection_succeeds_with_the_real_sdk_when_the_model_is_listed():
    client, requested = _client([config.LLM_MODEL, "llama-3.1-8b-instant"])
    msg = GroqLLM("test-key-not-real", client=client).test_connection()
    assert config.LLM_MODEL in msg
    assert requested == ["/openai/v1/models"], "must not call the slash-encoded retrieve path"


def test_connection_reports_not_found_when_the_model_is_missing():
    client, _ = _client(["llama-3.1-8b-instant"])
    with pytest.raises(LLMError) as err:
        GroqLLM("test-key-not-real", client=client).test_connection()
    assert err.value.kind == "not_found"
