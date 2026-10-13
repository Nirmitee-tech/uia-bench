"""Actions the model emits and the executor performs.

An action targets a control by `identity` (role + label), never by raw index or
pixel. That choice is what lets a recorded flow replay with no model: identity
survives between captures; index and pixels do not. Coordinate clicks exist only
as the vision-only fallback for screens with no accessibility tree.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Action:
    kind: str                       # click | type | read | press_key
    target_identity: Optional[str] = None   # preferred: role::label
    text: Optional[str] = None      # for type / press_key
    xy: Optional[tuple] = None      # vision-only fallback when identity is None


class ActionError(Exception):
    pass


class Executor:
    """Resolves an action against the current skyshot and applies it.

    Against the fixture adapter this mutates an in-memory screen so tasks and
    replay are deterministic. Against the macOS adapter the same calls become
    CGEvent clicks and keystrokes. Resolution is the honest part: if the target
    identity is not in the skyshot, we raise rather than click the nearest thing.
    That failure is what the heal loop catches.
    """

    def __init__(self, adapter):
        self.adapter = adapter

    def perform(self, action: Action, sky) -> Optional[str]:
        if action.target_identity is not None:
            el = sky.by_identity(action.target_identity)
            if el is None:
                raise ActionError(f"target not found: {action.target_identity}")
            if not el.enabled:
                raise ActionError(f"target disabled: {action.target_identity}")
            return self.adapter.apply(action, el, sky)
        # vision-only fallback: no stable identity, click a coordinate
        if action.xy is None:
            raise ActionError("action has neither identity nor coordinate")
        return self.adapter.apply_xy(action, action.xy, sky)
