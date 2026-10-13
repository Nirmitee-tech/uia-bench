"""Heal a broken recording.

When replay raises because a target identity is gone, the healer tries to
re-resolve it from the live skyshot and rewrite the recording. The strategy
here is deliberately simple and conservative: match on the same role plus the
closest label (same leading token, or an enabled control of that role when the
window has exactly one). A real build would call the model for ambiguous cases;
this heuristic covers the common case and proves the record -> break ->
re-resolve -> re-save loop end to end; a model handles ambiguous cases.

What this catches: a renamed or moved button whose role and purpose are intact.
What this does NOT catch: a genuinely different workflow. We return None then,
rather than guess, so the suite can tell a real heal from a lucky click.
"""
from __future__ import annotations

from typing import Optional

from .actions import Action
from .recorder import Recording
from .skyshot import Skyshot


def _reresolve(old_identity: str, sky: Skyshot) -> Optional[str]:
    role, _, old_label = old_identity.partition("::")
    candidates = [e for e in sky.elements if e.role == role and e.enabled]
    if not candidates:
        return None
    # exactly one control of this role: unambiguous, take it
    if len(candidates) == 1:
        return candidates[0].identity
    # otherwise prefer a label sharing the first word with the old one
    old_head = old_label.split()[0].lower() if old_label.split() else ""
    for e in candidates:
        head = e.label.split()[0].lower() if e.label.split() else ""
        # a renamed control usually keeps its leading word as a prefix:
        # "Labs" -> "Lab Results" shares the stem "lab". Match either direction.
        if head and old_head and (head.startswith(old_head) or old_head.startswith(head)):
            return e.identity
    return None


def heal(recording: Recording, broken: Action, sky: Skyshot) -> Optional[Recording]:
    """Return a rewritten recording if the broken action can be re-resolved."""
    if broken.target_identity is None:
        return None
    new_identity = _reresolve(broken.target_identity, sky)
    if new_identity is None:
        return None
    new_actions = []
    for a in recording.actions:
        if a is broken or a.target_identity == broken.target_identity:
            new_actions.append(Action(kind=a.kind, target_identity=new_identity,
                                      text=a.text, xy=a.xy))
        else:
            new_actions.append(a)
    return Recording(name=recording.name, app=recording.app,
                     window_title=recording.window_title, actions=new_actions)
