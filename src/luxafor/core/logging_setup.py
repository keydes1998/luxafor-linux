"""Logging setup with optional redaction of secrets."""
from __future__ import annotations

import logging
import logging.handlers
import re

from luxafor.core import config

_TOKEN_RE = re.compile(r"(?i)(authorization|access_token|refresh_token|client_secret|bearer|token)[^\s]*")


class RedactingFilter(logging.Filter):
    """Removes anything token-like from log records; never logs raw tokens."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
            if _TOKEN_RE.search(msg):
                record.msg = "[redacted]" + _TOKEN_RE.sub("[redacted]", msg)
                record.args = ()
        except Exception:
            pass
        return True


def setup_logging(level: str = "INFO", console: bool = True) -> logging.Logger:
    config.ensure_dirs()
    root = logging.getLogger("luxafor")
    if getattr(root, "_luxafor_configured", False):
        root.setLevel(getattr(logging, level.upper(), logging.INFO))
        return root
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    redact = RedactingFilter()
    fh = logging.handlers.RotatingFileHandler(
        config.LOG_PATH, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    fh.addFilter(redact)
    root.addHandler(fh)
    if console:
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        ch.addFilter(redact)
        root.addHandler(ch)
    root._luxafor_configured = True
    return root


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger("luxafor." + name)