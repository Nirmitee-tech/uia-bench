#!/usr/bin/env python3
"""uia — a model-agnostic framework for UI-driven integration.

Drive an application through its screen the way a person does, for systems with
no API. A model teaches a flow once; the flow then replays with no model and
heals itself when the screen changes. Any model plugs in as the teacher.

Commands:
    uia bench                         run the test suite (fixture control case)
    uia scan "App"                    report a live Mac app's AX coverage
    uia learn "App" "goal" --driver openai|anthropic|local [--out flow.json]
    uia replay flow.json              replay a saved flow with no model
    uia drivers                       list available teachers

Standard library only. macOS Accessibility permission is needed for scan/learn/
replay against a live app. Set a model with env, e.g. OPENAI_API_KEY, or point
UIA_LOCAL_BASE at a local server to keep data on the machine.
"""
import json
import sys

from engine.actions import Action, Executor
from engine.adapters.macos import MacosAdapter
from engine.driver import DRIVERS, learn as learn_loop
from engine.recorder import Recording, replay


def cmd_bench(argv):
    from bench import main
    return main()


def cmd_scan(argv):
    import scan
    sys.argv = ["scan", argv[0]] if argv else ["scan"]
    return scan.main()


def cmd_drivers(argv):
    print("available teachers:")
    for name in DRIVERS:
        print(f"  {name}")
    print("\nset the model with env: OPENAI_API_KEY / ANTHROPIC_API_KEY,")
    print("or UIA_LOCAL_BASE + UIA_LOCAL_MODEL for a local, on-box model.")
    return 0


def cmd_learn(argv):
    if len(argv) < 2:
        print('usage: uia learn "App" "goal" [--driver openai] [--out flow.json]')
        return 2
    app, goal = argv[0], argv[1]
    driver_name = _opt(argv, "--driver", "openai")
    out = _opt(argv, "--out", "flow.json")
    if driver_name not in DRIVERS:
        print(f"unknown driver: {driver_name}; see 'uia drivers'")
        return 2
    adapter = MacosAdapter()
    driver = DRIVERS[driver_name]()
    sky = adapter.capture(app, "")
    actions = learn_loop(goal, driver, Executor(adapter), adapter, app,
                         sky.window_title)
    rec = Recording(name=goal, app=app, window_title=sky.window_title,
                    actions=actions)
    _save(rec, out)
    print(f"learned {len(actions)} steps (teacher: {driver.name}) -> {out}")
    return 0


def cmd_replay(argv):
    if not argv:
        print("usage: uia replay flow.json")
        return 2
    rec = _load(argv[0])
    adapter = MacosAdapter()
    results = replay(rec, Executor(adapter), adapter)
    print(f"replayed {len(rec.actions)} steps with no model")
    for r in results:
        print(f"  read: {r}")
    return 0


# --- small helpers ------------------------------------------------------------
def _opt(argv, flag, default):
    return argv[argv.index(flag) + 1] if flag in argv else default


def _save(rec: Recording, path: str):
    data = {"name": rec.name, "app": rec.app, "window_title": rec.window_title,
            "actions": [a.__dict__ for a in rec.actions]}
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _load(path: str) -> Recording:
    with open(path) as f:
        d = json.load(f)
    actions = [Action(**a) for a in d["actions"]]
    return Recording(d["name"], d["app"], d["window_title"], actions)


COMMANDS = {"bench": cmd_bench, "scan": cmd_scan, "drivers": cmd_drivers,
            "learn": cmd_learn, "replay": cmd_replay}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        return 0 if len(sys.argv) < 2 else 2
    return COMMANDS[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    sys.exit(main())
