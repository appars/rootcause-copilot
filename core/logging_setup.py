"""Safe technical logging.

* Technical details (exception types, stack traces) go to a log file for the
  instructor - never to the student's screen.
* Every record passes through a redaction filter that removes anything that
  looks like a Groq API key, plus any key value registered at runtime.
* If the log directory cannot be created (read-only folder, permissions),
  logging falls back to stderr instead of crashing the app.
"""
from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler

import config

_KEY_PATTERNS = [
    re.compile(r"gsk_[A-Za-z0-9_\-]{8,}"),                         # Groq key format
    re.compile(r"(?i)(api[_-]?key|authorization|bearer)\s*[:=]\s*\S+"),
]
_registered_secrets: set[str] = set()
REDACTED = "[REDACTED]"


def register_secret(value: str | None) -> None:
    """Remember a secret value (e.g. the session API key) so it is redacted from logs."""
    if value and len(value) >= 8:
        _registered_secrets.add(value)


def forget_secret(value: str | None) -> None:
    _registered_secrets.discard(value or "")


def redact(text: str) -> str:
    for secret in _registered_secrets:
        text = text.replace(secret, REDACTED)
    for rx in _KEY_PATTERNS:
        text = rx.sub(REDACTED, text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(str(record.msg))
        if record.args:
            record.args = tuple(redact(str(a)) for a in record.args) if isinstance(record.args, tuple) else record.args
        if record.exc_info and record.exc_info[1] is not None:
            # Render the traceback now so it can be redacted, then drop the raw exception.
            formatted = logging.Formatter().formatException(record.exc_info)
            record.msg = f"{record.msg}\n{redact(formatted)}"
            record.exc_info = None
            record.exc_text = None
        return True


_configured = False


def get_logger(name: str = "rootcause") -> logging.Logger:
    """Return the app logger, configuring handlers once."""
    global _configured
    logger = logging.getLogger("rootcause")
    if not _configured:
        logger.setLevel(logging.INFO)
        logger.propagate = False
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        handler: logging.Handler
        try:
            config.LOG_DIR.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(config.LOG_DIR / "app.log", maxBytes=1_000_000, backupCount=3,
                                          encoding="utf-8")
        except OSError:
            handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(fmt)
        handler.addFilter(RedactingFilter())
        logger.addHandler(handler)
        _configured = True
    return logger if name == "rootcause" else logger.getChild(name.replace("rootcause.", ""))
