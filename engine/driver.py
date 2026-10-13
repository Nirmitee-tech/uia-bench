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
# Each is a thin wrapper over the model client. It asks a live model for one step
# and parses the reply into a validated Action. They differ only in which model
# config they carry, which is the whole point: the teacher is swappable data, not
# code. parse_action refuses any control not present in the skyshot, so a model
# never clicks something that is not on screen.

class ModelDriver:
    """A driver backed by any configured model (OpenAI-compatible or Anthropic)."""

    def __init__(self, name: str, cfg):
        self.name = name
        self.cfg = cfg

    def next_action(self, goal: str, sky: Skyshot, history: list) -> Optional[Action]:
        from .llm import call_model, parse_action
        reply = call_model(self.cfg, goal, sky, history)
        return parse_action(reply, sky)


def openai_driver() -> ModelDriver:
    """Teacher = OpenAI / Codex, or any OpenAI-compatible endpoint via env."""
    from .llm import openai_cfg
    return ModelDriver("openai", openai_cfg())


def anthropic_driver() -> ModelDriver:
    """Teacher = Claude via the Anthropic API."""
    from .llm import anthropic_cfg
    return ModelDriver("anthropic", anthropic_cfg())


def local_driver() -> ModelDriver:
    """Teacher = a local vision model, so no patient data leaves the machine."""
    from .llm import local_cfg
    return ModelDriver("local-vlm", local_cfg())


class VisionDriver:
    """Teacher for pixels-only screens: RDP, Citrix, canvas apps, games.

    Captures the window as an image and asks a vision model for a coordinate.
    Needs the skyshot's window_bounds, which the macOS provider supplies. This is
    the path that works where no accessibility tree exists -- the exact case a
    remote-desktop EHR presents.
    """

    def __init__(self, cfg):
        self.name = "vision"
        self.cfg = cfg

    def next_action(self, goal: str, sky: Skyshot, history: list) -> Optional[Action]:
        from .vision import capture_window, call_vision, parse_vision_action
        if not sky.window_bounds:
            raise ValueError("vision path needs window_bounds; none on this skyshot")
        x, y, w, h = sky.window_bounds
        path, _ = capture_window(sky.window_bounds)
        reply = call_vision(self.cfg, goal, path, (int(w), int(h)), history)
        return parse_vision_action(reply, (x, y))


class AutoDriver:
    """The Codex lesson, fused: use elements when present, vision when not.

    If the skyshot exposes an accessibility tree, grounding on a named control is
    more reliable, so we use the model driver. If the tree is empty, we fall back
    to the vision driver. One driver that adapts per screen, which is what makes
    the same flow reach both a native app and a remote desktop.
    """

    def __init__(self, element_cfg, vision_cfg):
        self.name = "auto"
        self._element = ModelDriver("auto-element", element_cfg)
        self._vision = VisionDriver(vision_cfg)

    def next_action(self, goal: str, sky: Skyshot, history: list) -> Optional[Action]:
        if sky.ax_available and sky.elements:
            return self._element.next_action(goal, sky, history)
        return self._vision.next_action(goal, sky, history)


def vision_driver() -> VisionDriver:
    from .llm import openai_cfg
    return VisionDriver(openai_cfg())


def auto_driver() -> AutoDriver:
    from .llm import openai_cfg
    return AutoDriver(openai_cfg(), openai_cfg())


DRIVERS = {"openai": openai_driver, "anthropic": anthropic_driver,
           "local": local_driver, "vision": vision_driver, "auto": auto_driver}


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
