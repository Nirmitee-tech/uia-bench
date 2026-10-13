"""Skyshot: the fused view a model acts on.

A skyshot is a screenshot plus the accessibility tree (the OS's named list of
on-screen controls), with every actionable control given a stable index. This
is the piece that makes element-targeted clicking possible instead of guessing
pixels. See the teardown note in README.md for why Codex's effectiveness rests
on this fusion.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol


@dataclass(frozen=True)
class Element:
    """One actionable control in the accessibility tree.

    `identity` is what record/replay anchors on. It is deliberately NOT the
    index (indexes shuffle between captures) and NOT pixel bounds (they move).
    It is a content-stable key: role plus the label a human reads. When a label
    changes, replay fails and the heal loop must re-resolve it.
    """
    index: int
    role: str          # AXButton, AXTextField, AXStaticText, ...
    label: str         # the AXTitle/AXDescription a human sees
    bounds: tuple      # (x, y, w, h) in screen coords; for vision fallback only
    enabled: bool = True
    value: Optional[str] = None

    @property
    def identity(self) -> str:
        return f"{self.role}::{self.label}"

    @property
    def center(self) -> tuple:
        x, y, w, h = self.bounds
        return (x + w / 2, y + h / 2)


@dataclass
class Skyshot:
    app: str
    window_title: str
    elements: list = field(default_factory=list)   # list[Element], indexed
    screenshot_sha256: Optional[str] = None        # proof a frame was captured
    ax_available: bool = True                       # False => vision-only screen
    window_bounds: Optional[tuple] = None           # (x, y, w, h) of the window, points
    screenshot_path: Optional[str] = None           # captured frame for the vision path

    def by_identity(self, identity: str) -> Optional[Element]:
        for e in self.elements:
            if e.identity == identity:
                return e
        return None

    def by_label(self, label: str) -> Optional[Element]:
        for e in self.elements:
            if e.label == label:
                return e
        return None


class SkyshotProvider(Protocol):
    """Anything that can produce a skyshot for a target window.

    The fixture provider replays recorded gold captures (deterministic, used by
    the suite). The macOS provider shells out to the Swift `skyshot` CLI that
    walks AXUIElement and grabs a ScreenCaptureKit frame. Same interface, so the
    seven test classes never change when we swap in the real machine.
    """
    def capture(self, app: str, window_title: str) -> Skyshot: ...
