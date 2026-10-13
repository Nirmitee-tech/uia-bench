#!/usr/bin/env python3
"""Run perception against a LIVE Mac app and report AX coverage.

Usage:
    python3 scan.py "Finder"
    python3 scan.py "athenahealth"      # once an EHR window is open

This is the first real-world measurement the suite was built for: does a given
app expose a usable accessibility tree, and how many actionable controls does
the skyshot see. It reads only; it never clicks. Use it to triage which EHRs are
AX-rich (element clicks will work) versus vision-only (the hard case).
"""
import sys

from engine.adapters.macos import MacosAdapter


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python3 scan.py \"App Name\"")
        return 2
    app = sys.argv[1]
    sky = MacosAdapter().capture(app, "")
    roles = {}
    for e in sky.elements:
        roles[e.role] = roles.get(e.role, 0) + 1
    print(f"\napp: {sky.app}")
    print(f"window: {sky.window_title or '(untitled)'}")
    print(f"ax_available: {sky.ax_available}")
    print(f"controls seen: {len(sky.elements)}")
    for role, n in sorted(roles.items(), key=lambda kv: -kv[1]):
        print(f"  {role:<16} {n}")
    actionable = sum(1 for e in sky.elements
                     if e.role in {"AXButton", "AXTextField", "AXPopUpButton",
                                   "AXCheckBox", "AXLink", "AXMenuItem"})
    verdict = "AX-rich: element clicks viable" if actionable >= 3 \
        else "sparse: expect vision-only fallback"
    print(f"\nactionable controls: {actionable}  ->  {verdict}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
