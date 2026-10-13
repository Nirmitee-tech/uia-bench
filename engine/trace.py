"""Run trace: a readable record of exactly what a flow did.

Measurement only means something if a human can inspect the run. A trace records
each step -- the action, its result, the risk level, and an optional screenshot
path -- and writes both a JSON record and a plain HTML report. For an EHR
integration this is the evidence artifact: what the system clicked, read, and
when, reviewable without rerunning anything.
"""
from __future__ import annotations

import html
import json
import time

from .redaction import redact
from dataclasses import dataclass, field


@dataclass
class Step:
    n: int
    kind: str
    target: str
    result: str
    risk: str = "safe"
    screenshot: str = ""
    ts: float = field(default_factory=time.time)


@dataclass
class Trace:
    name: str
    steps: list = field(default_factory=list)

    def add(self, kind: str, target: str, result="", risk="safe", screenshot="",
            secrets=None):
        # redact before storing: a trace must never become a copy of secrets
        self.steps.append(Step(len(self.steps) + 1, kind, redact(target, secrets),
                               redact("" if result is None else result, secrets),
                               risk, screenshot))

    def to_json(self, path: str):
        with open(path, "w") as f:
            json.dump({"name": self.name,
                       "steps": [s.__dict__ for s in self.steps]}, f, indent=2)

    def to_html(self, path: str):
        rows = []
        for s in self.steps:
            shot = f'<img src="{html.escape(s.screenshot)}" width="320">' if s.screenshot else ""
            rows.append(
                f"<tr><td>{s.n}</td><td>{html.escape(s.kind)}</td>"
                f"<td>{html.escape(s.target)}</td><td>{html.escape(s.result)}</td>"
                f"<td>{html.escape(s.risk)}</td><td>{shot}</td></tr>")
        doc = (
            "<!doctype html><meta charset=utf-8><title>Run trace: "
            f"{html.escape(self.name)}</title>"
            "<style>body{font:14px system-ui;margin:2rem;background:#fff;color:#111}"
            "table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;"
            "padding:6px 10px;text-align:left;vertical-align:top}"
            "th{background:#f4f4f5}</style>"
            f"<h1>Run trace: {html.escape(self.name)}</h1>"
            f"<p>{len(self.steps)} steps</p><table>"
            "<tr><th>#</th><th>action</th><th>target</th><th>result</th>"
            "<th>risk</th><th>screenshot</th></tr>" + "".join(rows) + "</table>")
        with open(path, "w") as f:
            f.write(doc)
