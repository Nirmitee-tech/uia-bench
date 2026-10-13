"""Fixture adapter: a deterministic in-memory app built from a gold JSON screen.

This is the control case. It lets the whole suite run green with no Mac
permissions and no real EHR, so the harness is testable the day it exists. The
real macOS adapter (native/skyshot) implements the same two methods against a
live window; swapping it in changes nothing in the seven test classes.

The fixture models a tiny screen with a mutable text field, so that type/read
actions have an observable effect and tasks can succeed or fail honestly.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy

from ..actions import Action, ActionError
from ..skyshot import Element, Skyshot


class FixtureAdapter:
    def __init__(self, gold_path: str):
        with open(gold_path) as f:
            self._gold = json.load(f)
        # live mutable state keyed by element label -> value
        self._state = {}
        for raw in self._gold["elements"]:
            if raw.get("value") is not None:
                self._state[raw["label"]] = raw["value"]
        self._mutations = []   # list of callables applied to each capture

    def add_mutation(self, fn):
        """Register a screen change (used by the heal test to rename a control)."""
        self._mutations.append(fn)

    def capture(self, app: str, window_title: str) -> Skyshot:
        raw_elements = deepcopy(self._gold["elements"])
        for fn in self._mutations:
            raw_elements = fn(raw_elements)
        elements = []
        for i, r in enumerate(raw_elements):
            label = r["label"]
            elements.append(Element(
                index=i, role=r["role"], label=label,
                bounds=tuple(r["bounds"]), enabled=r.get("enabled", True),
                value=self._state.get(label, r.get("value")),
            ))
        blob = json.dumps(raw_elements, sort_keys=True).encode()
        return Skyshot(
            app=self._gold["app"], window_title=self._gold["window_title"],
            elements=elements, screenshot_sha256=hashlib.sha256(blob).hexdigest(),
            ax_available=self._gold.get("ax_available", True),
        )

    def apply(self, action: Action, el: Element, sky: Skyshot):
        if action.kind == "read":
            return el.value
        if action.kind == "type":
            self._state[el.label] = action.text
            return None
        if action.kind == "click":
            # a click on a labeled "compute" control writes a derived value,
            # so a task like "read the result after acting" is observable
            if el.label == "Equals" and "Entry" in self._state:
                self._state["Result"] = self._state.get("Entry", "")
            return None
        if action.kind == "press_key":
            return None
        raise ActionError(f"unknown action kind: {action.kind}")

    def apply_xy(self, action: Action, xy: tuple, sky: Skyshot):
        # vision-only path: we cannot verify what we hit, so reads are unknown
        if action.kind == "read":
            return None
        return None
