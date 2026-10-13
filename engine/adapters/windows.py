"""Windows desktop adapter: the same contract, via Windows UI Automation.

The core is domain-neutral and platform-neutral; only the desktop adapter is
platform-specific. This one reads the Windows UI Automation tree (the OS's named
control list, the Windows equal of macOS accessibility) and sends input, so a
flow learned on Windows uses the identical Skyshot/Element/Action types and the
same drivers, record/replay, heal, and measurement.

It uses the `uiautomation` package, installed as the optional `windows` extra
(`pip install nirmitee-control[windows]`), rather than the standard library,
because Windows UI Automation has no stdlib binding. The browser (CDP) path,
the flow API, and MCP need no extra and already run on Windows as-is.
"""
from __future__ import annotations

from ..actions import Action, ActionError
from ..skyshot import Element, Skyshot

_KEEP = {"ButtonControl", "EditControl", "TextControl", "CheckBoxControl",
         "RadioButtonControl", "ComboBoxControl", "MenuItemControl",
         "HyperlinkControl", "ListItemControl", "TabItemControl"}


def _require():
    try:
        import uiautomation as auto  # noqa: F401
        return auto
    except ImportError as e:  # clear message rather than a cryptic failure
        raise ImportError(
            "the Windows desktop adapter needs the 'windows' extra: "
            "pip install nirmitee-control[windows]") from e


class WindowsAdapter:
    def __init__(self):
        self.auto = _require()

    def _window(self, app: str):
        # match the top window whose process or name contains `app`
        root = self.auto.GetRootControl()
        for w in root.GetChildren():
            if app.lower() in (w.Name or "").lower() or app.lower() in (w.ClassName or "").lower():
                return w
        return self.auto.GetForegroundControl()

    def capture(self, app: str, window_title: str = "") -> Skyshot:
        auto = self.auto
        win = self._window(app)
        elements, i = [], 0

        def walk(ctrl, depth=0):
            nonlocal i
            if depth > 40:
                return
            try:
                ctype = ctrl.ControlTypeName
                name = ctrl.Name or ""
                if ctype in _KEEP and name:
                    r = ctrl.BoundingRectangle
                    elements.append(Element(
                        index=i, role=ctype, label=name,
                        bounds=(r.left, r.top, r.width(), r.height()),
                        enabled=ctrl.IsEnabled,
                        value=getattr(ctrl, "GetValuePattern", lambda: None) and None))
                    i += 1
                for child in ctrl.GetChildren():
                    walk(child, depth + 1)
            except Exception:  # noqa: BLE001 - a flaky node must not abort the walk
                return

        walk(win)
        title = win.Name if win else window_title
        wb = None
        if win:
            r = win.BoundingRectangle
            wb = (r.left, r.top, r.width(), r.height())
        return Skyshot(app=app, window_title=title, elements=elements,
                       ax_available=bool(elements), window_bounds=wb)

    def _find(self, el: Element):
        auto = self.auto
        return auto.ControlFromCursor and None  # resolution happens by name below

    def apply(self, action: Action, el: Element, sky: Skyshot):
        auto = self.auto
        # re-resolve the control by name+type at action time
        ctrl = auto.Control(searchDepth=0)
        target = None
        root = self._window(sky.app)

        def find(c, depth=0):
            nonlocal target
            if target or depth > 40:
                return
            if c.Name == el.label and c.ControlTypeName == el.role:
                target = c
                return
            for ch in c.GetChildren():
                find(ch, depth + 1)

        find(root)
        if target is None:
            raise ActionError(f"target not found: {el.identity}")
        if action.kind == "read":
            try:
                return target.GetValuePattern().Value
            except Exception:
                return target.Name
        if action.kind == "click":
            target.Click(simulateMove=False)
            return None
        if action.kind == "type":
            target.SetFocus()
            auto.SendKeys(action.text or "")
            return None
        if action.kind == "press_key":
            auto.SendKeys(action.text or "{Enter}")
            return None
        raise ActionError(f"unknown action kind: {action.kind}")

    def apply_xy(self, action: Action, xy: tuple, sky: Skyshot):
        auto = self.auto
        if action.kind == "click":
            auto.Click(int(xy[0]), int(xy[1]))
            return None
        raise ActionError("vision-only read is not supported on Windows adapter")
