"""Action risk policy, approval gate, and audit log.

Codex runs a confirmations policy before risky or data-sharing actions, but the
user never sees its rules. Ours is open and auditable, which for healthcare is a
real advantage: a reviewer can read exactly when the system pauses for a human
and can replay the full audit trail of what it did.

The policy classifies an action into a risk level with a reason. A gate asks a
human before anything above a threshold. An audit log records every action and
every decision as one JSON line, so a run is fully accountable after the fact.
This is a framework, not a legal control: it enforces what the integrator
configures, and the audit proves what happened.
"""
from __future__ import annotations

import json
import time

from .redaction import redact
from dataclasses import dataclass
from typing import Callable, Optional

from .actions import Action, Executor

# risk order, low to high
LEVELS = ["safe", "write", "transmit", "destructive", "handoff"]


@dataclass
class Risk:
    level: str
    reason: str


def classify(action: Action, context: str = "") -> Risk:
    """Classify one action. Conservative: when unsure, rate higher.

    A read is safe. Typing or clicking is a write. A click whose target or the
    page context looks like sending data to someone else is a transmit. Words
    that signal deletion or irreversible submission raise it further. The caller
    supplies `context` (e.g. the target label) so the check sees intent, not just
    the verb.
    """
    text = f"{action.target_identity or ''} {action.text or ''} {context}".lower()
    if action.kind == "read":
        return Risk("safe", "reads do not change or share data")
    if any(w in text for w in ("delete", "remove", "discard", "empty trash",
                               "cancel appointment", "permanently")):
        return Risk("destructive", "wording signals deletion or an irreversible change")
    if any(w in text for w in ("password", "otp", "2fa", "ssn", "card number",
                               "bypass", "not secure", "captcha")):
        return Risk("handoff", "credential, safety-barrier, or CAPTCHA step; a human must do it")
    if any(w in text for w in ("send", "submit", "post", "share", "upload",
                               "pay", "transfer", "email")):
        return Risk("transmit", "may share data with a third party")
    if action.kind in ("type", "click", "press_key"):
        return Risk("write", "changes on-screen state")
    return Risk("write", "default to write when unclear")


class PolicyExecutor:
    """Wraps an Executor: classify, gate above threshold, audit every action.

    `gate(action, risk)` returns True to proceed. Default threshold pauses on
    transmit and above; handoff always refuses (a human must take over). The
    audit log is append-only JSON lines.
    """

    def __init__(self, inner: Executor, audit_path: str = "audit.jsonl",
                 gate: Optional[Callable[[Action, Risk], bool]] = None,
                 pause_from: str = "transmit"):
        self.inner = inner
        self.audit_path = audit_path
        self.gate = gate or (lambda a, r: False)  # default: deny anything gated
        self.pause_from = pause_from

    def _audit(self, record: dict):
        record["ts"] = time.time()
        # audit records what happened, never the sensitive values involved
        if record.get("target") is not None:
            record["target"] = redact(record["target"])
        with open(self.audit_path, "a") as f:
            f.write(json.dumps(record) + "\n")

    def perform(self, action: Action, sky, context: str = ""):
        risk = classify(action, context)
        threshold = LEVELS.index(self.pause_from)
        decision = "auto"
        if risk.level == "handoff":
            self._audit({"action": action.kind, "target": action.target_identity,
                         "risk": risk.level, "reason": risk.reason, "decision": "refused"})
            raise PermissionError(f"handoff required: {risk.reason}")
        if LEVELS.index(risk.level) >= threshold:
            allowed = self.gate(action, risk)
            decision = "approved" if allowed else "denied"
            self._audit({"action": action.kind, "target": action.target_identity,
                         "risk": risk.level, "reason": risk.reason, "decision": decision})
            if not allowed:
                raise PermissionError(f"not approved ({risk.level}): {risk.reason}")
            result = self.inner.perform(action, sky)
            return result
        result = self.inner.perform(action, sky)
        self._audit({"action": action.kind, "target": action.target_identity,
                     "risk": risk.level, "reason": risk.reason, "decision": decision})
        return result
