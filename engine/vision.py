"""The vision path: act on a screen that exposes no accessibility tree.

This is the Codex lesson made ours. When the accessibility tree is empty -- a
remote desktop (RDP/Citrix), a canvas app, a game -- there are no named controls
to click. So we capture the window as an image and ask a vision model where to
click, in coordinates. The click then lands through the same CGEvent executor.

Coordinates are the whole difficulty. We capture the window region, resize the
image to the window's point size so one image pixel equals one screen point,
then add the window's origin to get a global point. That keeps the model working
in the same frame it sees, and removes the Retina 2x mismatch that breaks naive
pixel clicking.

macOS tools only: `screencapture` grabs the region, `sips` resizes it. No extra
dependency. Screen Recording permission is required, the same as any capture.
"""
from __future__ import annotations

import base64
import hashlib
import os
import subprocess
import tempfile
from typing import Optional

from .actions import Action
from .llm import ModelConfig, _post

VISION_SYSTEM = (
    "You operate an application you can only see as an image. You are given a "
    "goal and a screenshot of one window, with its pixel width and height. "
    "Return ONE next step as strict JSON and nothing else:\n"
    '{"kind":"click|type|done","x":<int>,"y":<int>,"text":"<for type>"}\n'
    "x,y are pixel coordinates inside the image, origin top-left. Point at the "
    "center of the target. Return kind \"done\" when the goal is met."
)


def capture_window(window_bounds: tuple) -> tuple:
    """Capture a window region to a PNG sized in points. Returns (path, sha256).

    window_bounds is (x, y, w, h) in points. We capture, then force the image to
    exactly (w, h) pixels so image coordinates map 1:1 to screen points.
    """
    x, y, w, h = [int(round(v)) for v in window_bounds]
    fd, path = tempfile.mkstemp(suffix=".png", prefix="uia-frame-")
    os.close(fd)
    subprocess.run(["screencapture", "-x", "-R", f"{x},{y},{w},{h}", path],
                   check=True, capture_output=True)
    # normalise to point size so one image pixel == one screen point
    subprocess.run(["sips", "-z", str(h), str(w), path],
                   check=True, capture_output=True)
    with open(path, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    return path, sha


def _data_url(path: str) -> str:
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:image/png;base64,{b64}"


def call_vision(cfg: ModelConfig, goal: str, image_path: str,
                size: tuple, history: list, timeout: float = 90.0) -> str:
    """Ask a vision model for one step. OpenAI-compatible vision message shape."""
    w, h = size
    done = "; ".join(f"{a.kind}@{a.xy}" for a in history) or "(none yet)"
    text = (f"Goal: {goal}\nImage size: {w}x{h} pixels.\n"
            f"Steps so far: {done}\nReturn the next step as JSON.")
    if cfg.api != "openai":
        raise ValueError("vision path uses the OpenAI-compatible message shape; "
                         "set a vision-capable OpenAI/local model")
    headers = {"Content-Type": "application/json"}
    if cfg.key():
        headers["Authorization"] = f"Bearer {cfg.key()}"
    body = {"model": cfg.model, "temperature": 0, "messages": [
        {"role": "system", "content": VISION_SYSTEM},
        {"role": "user", "content": [
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": _data_url(image_path)}},
        ]},
    ]}
    out = _post(f"{cfg.base_url}/chat/completions", headers, body, timeout)
    return out["choices"][0]["message"]["content"]


def parse_vision_action(reply: str, window_origin: tuple) -> Optional[Action]:
    """Parse a vision reply into an Action with a GLOBAL coordinate, or None.

    The model returns image-relative pixels; we add the window origin so the
    click lands in the right place on the real screen. We validate the numbers
    are present and numeric, so a malformed reply fails rather than clicking 0,0.
    """
    import json
    text = reply.strip()
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1:
        raise ValueError(f"no JSON in vision reply: {reply!r}")
    obj = json.loads(text[s:e + 1])
    kind = obj.get("kind")
    if kind == "done":
        return None
    if kind not in {"click", "type"}:
        raise ValueError(f"unknown vision action kind: {kind!r}")
    ix, iy = obj.get("x"), obj.get("y")
    if not isinstance(ix, (int, float)) or not isinstance(iy, (int, float)):
        raise ValueError(f"vision reply missing numeric x,y: {obj!r}")
    ox, oy = window_origin
    return Action(kind=kind, xy=(ox + ix, oy + iy), text=obj.get("text"))
