"""macOS adapter: real skyshots and real input via the Swift `skyshot` CLI.

Capture shells out to the compiled native/skyshot binary and parses its JSON
into the same Skyshot the fixture adapter returns. Apply resolves a target's
on-screen center from its bounds and posts a real CGEvent click, keystroke, or
key press through the binary's `act` command.

Honest boundary: a `read` action reads the target's accessibility value from the
current skyshot rather than from pixels, so reads are exact where the tree is
rich and unavailable where it is not. A click lands at the control's center; on
a screen with no accessibility tree there is no center to compute, which is the
vision-only case the suite is built to flag before we rely on it.
"""
from __future__ import annotations

import json
import subprocess

from ..actions import Action, ActionError
from ..skyshot import Element, Skyshot

SKYSHOT_BIN = "native/skyshot/skyshot"


class MacosAdapter:
    def __init__(self, binary: str = SKYSHOT_BIN, background: bool = False):
        self.binary = binary
        # background=True delivers input to the target app's process, so it does
        # not move the hardware cursor or steal the user's focus. See the README
        # isolation note for its limits and full-isolation options.
        self.background = background

    def capture(self, app: str, window_title: str) -> Skyshot:
        proc = subprocess.run([self.binary, app], capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"skyshot failed: {proc.stderr.strip()}")
        raw = json.loads(proc.stdout)
        elements = [
            Element(index=i, role=r["role"], label=r["label"],
                    bounds=tuple(r["bounds"]), enabled=r.get("enabled", True),
                    value=r.get("value"))
            for i, r in enumerate(raw["elements"])
        ]
        wb = raw.get("window_bounds")
        return Skyshot(app=raw["app"], window_title=raw["window_title"],
                       elements=elements, ax_available=raw["ax_available"],
                       window_bounds=tuple(wb) if wb else None)

    def _act(self, app: str, *args: str):
        prefix = ["--bg"] if self.background else []
        proc = subprocess.run([self.binary, "act", app, *prefix, *args],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            raise ActionError(f"act failed: {proc.stderr.strip()}")

    def apply(self, action: Action, el: Element, sky: Skyshot):
        if action.kind == "read":
            return el.value
        if action.kind == "click":
            cx, cy = el.center
            self._act(sky.app, "click", str(cx), str(cy))
            return None
        if action.kind == "type":
            # focus the field first, then type into it
            cx, cy = el.center
            self._act(sky.app, "click", str(cx), str(cy))
            self._act(sky.app, "type", action.text or "")
            return None
        if action.kind == "press_key":
            self._act(sky.app, "key", action.text or "36")  # 36 = Return
            return None
        raise ActionError(f"unknown action kind: {action.kind}")

    def apply_xy(self, action: Action, xy: tuple, sky: Skyshot):
        # vision-only fallback: click raw coordinates, no element to verify
        if action.kind == "click":
            self._act(sky.app, "click", str(xy[0]), str(xy[1]))
            return None
        if action.kind == "type":
            self._act(sky.app, "type", action.text or "")
            return None
        raise ActionError("vision-only read is not supported; no element to read")
