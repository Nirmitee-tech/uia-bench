"""Record once, replay with no model.

A recording is just the ordered list of actions the learn phase produced. Replay
plays them back through the executor with the model switched off. Because each
action anchors on element identity, replay is deterministic as long as the
screen still exposes those controls. When an identity goes missing, replay
raises and hands off to the healer.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .actions import Action, ActionError, Executor


@dataclass
class Recording:
    name: str
    app: str
    window_title: str
    actions: list = field(default_factory=list)   # list[Action]


def replay(recording: Recording, executor: Executor, provider) -> list:
    """Replay a recording. Returns the list of read results. Raises on a break."""
    results = []
    for action in recording.actions:
        sky = provider.capture(recording.app, recording.window_title)
        out = executor.perform(action, sky)
        if action.kind == "read":
            results.append(out)
    return results


def replay_is_stable(recording: Recording, executor: Executor, provider, runs: int) -> bool:
    """True only if every run returns an identical read sequence and never raises."""
    first = None
    for _ in range(runs):
        try:
            out = replay(recording, executor, provider)
        except ActionError:
            return False
        if first is None:
            first = out
        elif out != first:
            return False
    return True
