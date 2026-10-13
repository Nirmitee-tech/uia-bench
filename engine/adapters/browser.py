"""Browser adapter: the DOM as a first-class target, reusing the whole pipeline.

This completes the DOM browser driver. Instead of a separate code path, a web
page becomes an ordinary adapter: capture() returns a Skyshot whose elements are
DOM controls (each identity is a CSS selector), and apply() performs clicks,
typing, and reads over the Chrome DevTools Protocol by selector. Because it is
the same Skyshot/Element/Executor contract, the model drivers, record/replay,
heal, and the measurement suite all work on the browser with no change.

Identity is a CSS selector here, not role::label, so a recorded web flow replays
against the DOM deterministically and heals when a selector's text changes.
"""
from __future__ import annotations

import json

from ..actions import Action, ActionError
from ..skyshot import Element, Skyshot

# one JS pass collects interactive controls with a stable-ish selector each
_COLLECT = r"""
(() => {
  const sel = (el) => {
    if (el.id) return '#' + CSS.escape(el.id);
    if (el.name) return el.tagName.toLowerCase() + '[name="' + el.name + '"]';
    const t = (el.innerText||el.value||'').trim().slice(0,40);
    return el.tagName.toLowerCase() + (t ? ':has-text(' + JSON.stringify(t) + ')' : '');
  };
  const nodes = [...document.querySelectorAll('button,a,input,select,textarea,[role=button],[onclick]')];
  return nodes.slice(0,200).map((el,i) => {
    const r = el.getBoundingClientRect();
    return {role: el.tagName.toLowerCase(),
            label: (el.innerText||el.getAttribute('aria-label')||el.value||el.name||'').trim().slice(0,80),
            selector: sel(el),
            bounds: [r.x, r.y, r.width, r.height],
            value: (el.value!==undefined ? el.value : null)};
  }).filter(e => e.label || e.selector);
})()
"""


class BrowserAdapter:
    """A Skyshot/apply adapter backed by a CDP session (or any object with eval)."""

    def __init__(self, session):
        self.session = session  # engine.browser_cdp.CDPSession, or any object with eval/title/click/type_into/text

    def capture(self, app: str = "browser", window_title: str = "") -> Skyshot:
        raw = self.session.eval(_COLLECT) or []
        # role carries the CSS selector (prefixed "css=") so the element identity
        # is the selector, which is what replay and heal anchor on for a page.
        elements = [
            Element(index=i, role=f"css={r['selector']}",
                    label=r["label"] or r["selector"],
                    bounds=tuple(r["bounds"]), value=r.get("value"))
            for i, r in enumerate(raw)
        ]
        title = self.session.title() if hasattr(self.session, "title") else window_title
        return Skyshot(app=app, window_title=title, elements=elements,
                       ax_available=True)

    def _selector(self, el: Element) -> str:
        return el.role[len("css="):] if el.role.startswith("css=") else el.role

    def apply(self, action: Action, el: Element, sky: Skyshot):
        selector = self._selector(el)
        if action.kind == "read":
            return self.session.text(selector)
        if action.kind == "click":
            if not self.session.click(selector):
                raise ActionError(f"no element for selector: {selector}")
            return None
        if action.kind == "type":
            if not self.session.type_into(selector, action.text or ""):
                raise ActionError(f"no input for selector: {selector}")
            return None
        if action.kind == "press_key":
            return None
        raise ActionError(f"unknown action kind: {action.kind}")

    def apply_xy(self, action: Action, xy: tuple, sky: Skyshot):
        raise ActionError("browser adapter acts by selector, not coordinate")
