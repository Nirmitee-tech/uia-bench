"""Flow-as-API: run a learned flow as a single callable, return structured data.

This is the platform's core promise made concrete. A learned flow is a sequence
of actions; this runs it through any adapter, fills parameters, collects the read
results, and returns one structured record. A system with no API now answers a
single call. The engine stays domain-neutral: a flow is just steps, and the
caller supplies the adapter and the parameters.

Parameters: an action's text may contain {{name}} placeholders; run_flow fills
them from the params dict before executing. Reads are returned keyed by step, so
one call yields a clean record the caller can map to whatever shape it needs.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional

from .actions import Action, Executor
from .recorder import Recording

_PARAM = re.compile(r"\{\{(\w+)\}\}")


@dataclass
class FlowResult:
    name: str
    status: str                 # "ok" or "error"
    reads: list                 # ordered read results
    steps: int
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {"name": self.name, "status": self.status, "reads": self.reads,
                "steps": self.steps, "error": self.error}


def _fill(text: Optional[str], params: dict) -> Optional[str]:
    if text is None:
        return None
    return _PARAM.sub(lambda m: str(params.get(m.group(1), m.group(0))), text)


def run_flow(recording: Recording, adapter, params: Optional[dict] = None) -> FlowResult:
    """Run a flow through an adapter and return the structured result.

    One call = one run. The adapter decides the target (fixture, macOS app, or
    browser); the flow and params are the same shape regardless. Errors are
    returned, not raised, so a caller behind an API gets a clean status.
    """
    params = params or {}
    ex = Executor(adapter)
    reads = []
    try:
        for a in recording.actions:
            action = Action(kind=a.kind, target_identity=a.target_identity,
                            text=_fill(a.text, params), xy=a.xy)
            sky = adapter.capture(recording.app, recording.window_title)
            out = ex.perform(action, sky)
            if a.kind == "read":
                reads.append(out)
        return FlowResult(recording.name, "ok", reads, len(recording.actions))
    except Exception as e:  # noqa: BLE001 - any adapter/action failure becomes status
        return FlowResult(recording.name, "error", reads, len(recording.actions),
                          error=f"{type(e).__name__}: {e}")


def load_flow(path: str) -> Recording:
    with open(path) as f:
        d = json.load(f)
    actions = [Action(**a) for a in d["actions"]]
    return Recording(d["name"], d["app"], d["window_title"], actions)
