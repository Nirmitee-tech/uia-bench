"""Model-agnostic driver contract.

The system must not depend on any one model. A driver is the only place a model
touches: given the current skyshot and a goal, it returns the next action. Claude
(via its Chrome extension), Codex (via its computer-use), and a local vision model
all implement this same one method. Everything below the driver -- record, replay,
heal, measure, PHI containment -- is identical no matter which model teaches.

Swap the teacher by swapping the driver. No other file changes. That is what
"agnostic" means here, in code rather than in a promise.
"""
from __future__ import annotations

from typing import Optional, Protocol

from .actions import Action
from .skyshot import Skyshot


class Driver(Protocol):
    """A model that proposes the next action toward a goal.

    `name` labels the teacher in recordings and in the scorecard, so a measured
    number always says which model produced it. `next_action` returns None when
    the model judges the goal complete.
    """
    name: str

    def next_action(self, goal: str, sky: Skyshot, history: list) -> Optional[Action]: ...


class ScriptedDriver:
    """A deterministic driver that replays a fixed action list.

    Not a model. It stands in for a teacher in tests and proves the contract:
    the recorder, executor and suite treat it exactly as they would Claude or
    Codex. The real drivers below return the same Action type from a live model.
    """
    name = "scripted"

    def __init__(self, actions: list):
        self._actions = list(actions)
        self._i = 0

    def next_action(self, goal: str, sky: Skyshot, history: list) -> Optional[Action]:
        if self._i >= len(self._actions):
            return None
        action = self._actions[self._i]
        self._i += 1
        return action


# --- real drivers: same contract, different teacher --------------------------
# Each is a thin adapter. It turns the skyshot into the model's input, asks the
# model for one step, and parses the reply back into an Action. None is wired to
# a live model yet; they are stubs that document the exact integration point, so
# adding a model is a small, isolated change, not a rewrite.

class ClaudeDriver:
    """Teacher = Claude via the Chrome extension (browser targets)."""
    name = "claude"

    def next_action(self, goal: str, sky: Skyshot, history: list) -> Optional[Action]:
        raise NotImplementedError(
            "wire to mcp__claude-in-chrome: send goal + skyshot, parse one action")


class CodexDriver:
    """Teacher = Codex computer-use (desktop and browser targets)."""
    name = "codex"

    def next_action(self, goal: str, sky: Skyshot, history: list) -> Optional[Action]:
        raise NotImplementedError(
            "wire to Codex computer-use: send goal + skyshot, parse one action")


class LocalVLMDriver:
    """Teacher = a local vision model, so PHI never leaves the machine."""
    name = "local-vlm"

    def __init__(self, endpoint: str):
        self.endpoint = endpoint

    def next_action(self, goal: str, sky: Skyshot, history: list) -> Optional[Action]:
        raise NotImplementedError(
            "wire to a local vision model endpoint: send goal + skyshot, parse one action")


def learn(goal: str, driver: Driver, executor, provider, app: str,
          window_title: str, max_steps: int = 40) -> list:
    """Run a teacher to completion and return the recorded action list.

    This is the whole learn phase, and it is agnostic: it never names a model,
    only calls driver.next_action. The returned list is a Recording's actions,
    ready to replay with no model at all.
    """
    recorded = []
    for _ in range(max_steps):
        sky = provider.capture(app, window_title)
        action = driver.next_action(goal, sky, recorded)
        if action is None:
            break
        executor.perform(action, sky)
        recorded.append(action)
    return recorded
