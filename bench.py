#!/usr/bin/env python3
"""Run the UI-automation bench and print a scorecard.

Usage:
    python3 bench.py

Runs the seven test classes against the fixture control case. Exit code is 0
only if every class passes its bar, so this can gate a build in CI. Point the
adapters at a live Mac window later; the runner does not change.
"""
import sys

from tests import suite


def main() -> int:
    print("\nUI-automation bench  ·  control case: fixture DemoEHR\n")
    width = max(len(fn.__name__) for fn in suite.ALL)
    all_pass = True
    for fn in suite.ALL:
        r = fn()
        mark = "PASS" if r.passed else "FAIL"
        all_pass = all_pass and r.passed
        print(f"  [{mark}]  {r.name:<{width}}  {r.measured:<22}  {r.note}")
    print()
    if all_pass:
        print("  All classes green. Harness is ready to point at real EHRs.\n")
        return 0
    print("  Some classes failed. Fix before extending to EHR targets.\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
