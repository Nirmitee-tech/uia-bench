"""Redaction: keep sensitive values out of traces and the audit log.

A trace and an audit log are evidence, and evidence must not become a second copy
of sensitive data. This masks values before they are recorded: anything that was
typed from a secret, plus pattern matches for common sensitive shapes (long
digit runs, emails, tokens). Redaction runs on the string that would be written,
so the on-screen data is still used to act but never stored in the clear.

This catches well-known shapes and injected secrets. It is a safety net, not a
guarantee that every sensitive value is caught, so a domain pack (for example a
healthcare pack) adds its own field rules on top. The README states that limit.
"""
from __future__ import annotations

import re

_PATTERNS = [
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[email]"),
    (re.compile(r"\b\d{12,19}\b"), "[number]"),          # card/account-length digit runs
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[id]"),      # SSN shape
    (re.compile(r"\b(?:sk|pk|ghp|xox[baprs])[-_][A-Za-z0-9]{10,}\b"), "[token]"),
    (re.compile(r"\b[A-Za-z0-9]{32,}\b"), "[token]"),    # long opaque tokens/keys
]


def redact(text, extra_values=None) -> str:
    """Mask known sensitive shapes and any provided literal values."""
    if text is None:
        return ""
    s = str(text)
    for val in (extra_values or []):
        if val:
            s = s.replace(str(val), "[redacted]")
    for pattern, tag in _PATTERNS:
        s = pattern.sub(tag, s)
    return s
