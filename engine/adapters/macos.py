"""macOS adapter: real skyshots from a live window via the Swift `skyshot` CLI.

Capture shells out to the compiled native/skyshot binary and parses its JSON
into the same Skyshot the fixture adapter returns. Action apply is a stub here:
wiring CGEvent clicks is the next build step, gated behind the perception and
grounding numbers the suite produces against real apps. We do not click a live
app until the suite shows we can see it correctly.

This file documents the boundary honestly: today it can SEE a live window
(read-only), it cannot yet ACT on one. The suite's perception and grounding
classes run against this adapter the moment the binary is built and permission
is granted; task/replay/heal stay on the fixture until action apply lands.
"""
from __future__ import annotations

import json
import subprocess

from ..actions import Action, ActionError
from ..skyshot import Element, Skyshot

SKYSHOT_BIN = "native/skyshot/skyshot"


class MacosAdapter:
    def __init__(self, binary: str = SKYSHOT_BIN):
        self.binary = binary

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
        return Skyshot(app=raw["app"], window_title=raw["window_title"],
                       elements=elements, ax_available=raw["ax_available"])

    def apply(self, action: Action, el: Element, sky: Skyshot):
        raise ActionError("macOS action apply not wired yet; see module docstring")

    def apply_xy(self, action: Action, xy: tuple, sky: Skyshot):
        raise ActionError("macOS vision-only apply not wired yet")
