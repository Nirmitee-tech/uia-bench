"""Real model client. Turns a skyshot plus a goal into one action.

Standard library only, so the framework installs with nothing but Python. The
client speaks two wire formats: OpenAI-compatible chat (OpenAI, Codex, Ollama,
LM Studio, vLLM, Together, Groq, and most local servers) and Anthropic messages.
That one real client is what makes the system model-agnostic: point it at a
different base URL and model, and the teacher changes with no other edit.

The model is asked for strict JSON describing one step. We parse it, validate it
against the controls actually present in the skyshot, and refuse anything that
does not resolve. A model that hallucinates a control fails closed here rather
than clicking the wrong thing.
"""
from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Optional

from .actions import Action
from .skyshot import Skyshot

SYSTEM = (
    "You operate an application through its accessibility tree. You are given a "
    "goal and the list of on-screen controls, each with an index, role, and "
    "label. Return ONE next step as strict JSON and nothing else:\n"
    '{"kind":"click|type|read|press_key|done",'
    '"target":"<exact label of the control>","text":"<for type/press_key>"}\n'
    "Use the exact label shown. Return kind \"done\" when the goal is met. "
    "Never invent a control that is not in the list."
)


def _render_controls(sky: Skyshot) -> str:
    lines = []
    for e in sky.elements:
        val = f" = {e.value!r}" if e.value is not None else ""
        lines.append(f"[{e.index}] {e.role} {e.label!r}{val}")
    return "\n".join(lines)


def _user_prompt(goal: str, sky: Skyshot, history: list) -> str:
    done = "; ".join(
        f"{a.kind}:{a.target_identity}" for a in history) or "(none yet)"
    return (
        f"Goal: {goal}\n\nApp: {sky.app}\nWindow: {sky.window_title}\n"
        f"ax_available: {sky.ax_available}\n\nControls:\n{_render_controls(sky)}\n\n"
        f"Steps so far: {done}\n\nReturn the next step as JSON."
    )


@dataclass
class ModelConfig:
    api: str          # "openai" or "anthropic"
    base_url: str
    model: str
    api_key_env: str  # name of the env var holding the key; empty for local

    def key(self) -> str:
        return os.environ.get(self.api_key_env, "") if self.api_key_env else ""


def _post(url: str, headers: dict, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def call_model(cfg: ModelConfig, goal: str, sky: Skyshot, history: list,
               timeout: float = 60.0) -> str:
    """Return the model's raw text reply. Raises on transport or auth failure."""
    user = _user_prompt(goal, sky, history)
    if cfg.api == "openai":
        headers = {"Content-Type": "application/json"}
        if cfg.key():
            headers["Authorization"] = f"Bearer {cfg.key()}"
        body = {"model": cfg.model, "temperature": 0,
                "messages": [{"role": "system", "content": SYSTEM},
                             {"role": "user", "content": user}]}
        out = _post(f"{cfg.base_url}/chat/completions", headers, body, timeout)
        return out["choices"][0]["message"]["content"]
    if cfg.api == "anthropic":
        headers = {"Content-Type": "application/json",
                   "anthropic-version": "2023-06-01"}
        if cfg.key():
            headers["x-api-key"] = cfg.key()
        body = {"model": cfg.model, "max_tokens": 512, "system": SYSTEM,
                "messages": [{"role": "user", "content": user}]}
        out = _post(f"{cfg.base_url}/messages", headers, body, timeout)
        return out["content"][0]["text"]
    raise ValueError(f"unknown api: {cfg.api}")


def parse_action(reply: str, sky: Skyshot) -> Optional[Action]:
    """Parse a model reply into a validated Action, or None for 'done'.

    Validation is the real guard: a click/type/read must name a control that is
    actually in this skyshot, matched by exact label. Anything else raises, so a
    wrong or hallucinated target never becomes a click.
    """
    text = reply.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON object in model reply: {reply!r}")
    obj = json.loads(text[start:end + 1])
    kind = obj.get("kind")
    if kind == "done":
        return None
    if kind not in {"click", "type", "read", "press_key"}:
        raise ValueError(f"unknown action kind from model: {kind!r}")
    if kind == "press_key":
        return Action(kind="press_key", text=obj.get("text"))
    label = obj.get("target")
    el = sky.by_label(label) if label else None
    if el is None:
        raise ValueError(f"model named a control not on screen: {label!r}")
    return Action(kind=kind, target_identity=el.identity, text=obj.get("text"))


# --- ready-made configs. Override base_url/model with env for anything else. ---
def openai_cfg() -> ModelConfig:
    return ModelConfig("openai",
                       os.environ.get("UIA_OPENAI_BASE", "https://api.openai.com/v1"),
                       os.environ.get("UIA_OPENAI_MODEL", "gpt-4o"),
                       "OPENAI_API_KEY")


def anthropic_cfg() -> ModelConfig:
    return ModelConfig("anthropic",
                       os.environ.get("UIA_ANTHROPIC_BASE", "https://api.anthropic.com/v1"),
                       os.environ.get("UIA_ANTHROPIC_MODEL", "claude-3-5-sonnet-latest"),
                       "ANTHROPIC_API_KEY")


def local_cfg() -> ModelConfig:
    # any OpenAI-compatible local server: Ollama, LM Studio, vLLM. No key, no PHI leaves.
    return ModelConfig("openai",
                       os.environ.get("UIA_LOCAL_BASE", "http://localhost:11434/v1"),
                       os.environ.get("UIA_LOCAL_MODEL", "qwen2.5vl"),
                       "")
