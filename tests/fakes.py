"""A fake Groq client so the Live LLM code path can be tested without network or cost."""
import json
from types import SimpleNamespace


def tool_response(name, args, call_id="call_1", content=""):
    tc = SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=json.dumps(args)))
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=[tc]))])


def text_response(content):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=None))])


def json_response(obj):
    return text_response(json.dumps(obj))


class RateLimitError(Exception):
    status_code = 429


class AuthenticationError(Exception):
    status_code = 401


class BadRequestError(Exception):
    status_code = 400

    def __init__(self, body=""):
        super().__init__(body)
        self.body = body


class FakeCompletions:
    def __init__(self, script):
        self.script = list(script)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        if not self.script:
            raise AssertionError("Fake Groq client ran out of scripted responses")
        item = self.script.pop(0)
        if callable(item) and not isinstance(item, type):
            item = item(kwargs)
        if isinstance(item, Exception):
            raise item
        return item


def fake_client(script):
    completions = FakeCompletions(script)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions),
                             models=SimpleNamespace(retrieve=lambda model: SimpleNamespace(id=model)))
    return client, completions


GOOD_DIAGNOSIS = {
    "hypothesis": "Requests wait for database connections because the pool is saturated.",
    "root_cause_category": "database_connection_pool",
    "supporting_evidence": ["L35: Pool stats (total=20, active=20, idle=0)"],
    "confidence": "medium", "alternatives": ["slow database server"], "missing_evidence": ["DB metrics"],
    "remediation": {"action": "Rolling restart and pause reporting job", "action_type": "restart_service",
                    "target": "payment-service", "expected_impact": "recovery", "risks": "brief errors",
                    "preconditions": "2+ replicas", "rollback": "n/a"},
}
SUPPORTED_REVIEW = {"verdict": "supported", "issues": [], "missing_evidence": [], "alternatives": [],
                    "confidence_justified": True, "suggested_confidence": "medium"}
