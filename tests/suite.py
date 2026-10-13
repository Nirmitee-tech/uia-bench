"""The seven test classes and their pass bars.

Each class returns a Result with the measured number and a pass/fail against a
bar fixed here, before any system is built. The point of the suite is to tell us
where the approach holds and where it breaks, with numbers, not opinion. Bars on
the fixture control case are strict (it is deterministic). Real EHR runs reuse
the same runners; their bars will be set from the first measured baseline, not
guessed here.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from engine.actions import Action, ActionError, Executor
from engine.adapters.fixture import FixtureAdapter
from engine.recorder import Recording, replay, replay_is_stable
from engine.healer import heal
from sandbox.egress_guard import NetworkGuard


@dataclass
class Result:
    name: str
    measured: str
    passed: bool
    note: str = ""


# --- gold labels: what a correct skyshot must contain for this screen ---------
GOLD_LABELS = {"Patient Name", "MRN", "DOB", "Problem List", "Labs",
               "Problem 1", "Lab A1c"}

# the 3 read-only tasks, scripted as action sequences against the fixture
TASKS = {
    "read_demographics": [
        Action("read", "AXStaticText::Patient Name"),
        Action("read", "AXStaticText::DOB"),
    ],
    "read_problem_list": [
        Action("click", "AXButton::Problem List"),
        Action("read", "AXStaticText::Problem 1"),
    ],
    "read_lab_result": [
        Action("click", "AXButton::Labs"),
        Action("read", "AXStaticText::Lab A1c"),
    ],
}
EXPECTED = {
    "read_demographics": ["TEST, PATIENT", "1990-01-01"],
    "read_problem_list": ["Hypertension"],
    "read_lab_result": ["6.4 %"],
}

GOLD = "tests/gold/ehr_patient_summary.json"
APP, WIN = "DemoEHR", "Patient Summary - TEST PATIENT (masked)"


def _provider():
    return FixtureAdapter(GOLD)


def perception() -> Result:
    sky = _provider().capture(APP, WIN)
    seen = {e.label for e in sky.elements}
    recall = len(GOLD_LABELS & seen) / len(GOLD_LABELS)
    return Result("perception", f"recall {recall:.0%}", recall >= 1.0,
                  "every gold control must appear on the control case")


def grounding() -> Result:
    sky = _provider().capture(APP, WIN)
    # resolving a known label must land on the control carrying that label
    hits = sum(1 for lbl in GOLD_LABELS
               if (e := sky.by_label(lbl)) and e.label == lbl)
    acc = hits / len(GOLD_LABELS)
    return Result("grounding", f"accuracy {acc:.0%}", acc >= 1.0,
                  "resolve the right control, not a neighbor")


def task_success() -> Result:
    adapter = _provider()
    ex = Executor(adapter)
    runs, ok = 20, 0
    for _ in range(runs):
        good = True
        for name, actions in TASKS.items():
            out = []
            for a in actions:
                sky = adapter.capture(APP, WIN)
                r = ex.perform(a, sky)
                if a.kind == "read":
                    out.append(r)
            if out != EXPECTED[name]:
                good = False
        ok += 1 if good else 0
    rate = ok / runs
    return Result("task_success", f"{ok}/{runs} runs", rate >= 1.0,
                  "3 read-only tasks end to end")


def replay_determinism() -> Result:
    adapter = _provider()
    ex = Executor(adapter)
    rec = Recording("read_lab_result", APP, WIN, TASKS["read_lab_result"])
    stable = replay_is_stable(rec, ex, adapter, runs=20)
    return Result("replay_determinism", "20/20 identical" if stable else "drift",
                  stable, "record once, replay model-off")


def heal_test() -> Result:
    # record against the original screen
    adapter = _provider()
    ex = Executor(adapter)
    rec = Recording("read_lab_result", APP, WIN, TASKS["read_lab_result"])

    # now the vendor renames the Labs button; replay must break, then heal
    def rename_labs(elements):
        for e in elements:
            if e["label"] == "Labs":
                e["label"] = "Lab Results"
        return elements

    broken_adapter = _provider()
    broken_adapter.add_mutation(rename_labs)
    broke = False
    try:
        replay(rec, Executor(broken_adapter), broken_adapter)
    except ActionError:
        broke = True
    if not broke:
        return Result("heal", "did not break", False, "mutation should break replay")

    sky = broken_adapter.capture(APP, WIN)
    broken_action = rec.actions[0]            # the click on the renamed button
    fixed = heal(rec, broken_action, sky)
    if fixed is None:
        return Result("heal", "no re-resolve", False, "healer failed to recover")
    try:
        out = replay(fixed, Executor(broken_adapter), broken_adapter)
    except ActionError:
        return Result("heal", "re-save failed", False, "healed recording still breaks")
    ok = out == EXPECTED["read_lab_result"]
    return Result("heal", "recovered" if ok else "wrong result", ok,
                  "rename a control, auto re-resolve and re-save")


def phi_containment() -> Result:
    adapter = _provider()
    ex = Executor(adapter)
    with NetworkGuard() as guard:
        for name, actions in TASKS.items():
            for a in actions:
                sky = adapter.capture(APP, WIN)
                ex.perform(a, sky)
    return Result("phi_containment",
                  f"{len(guard.attempts)} egress attempts",
                  not guard.leaked,
                  "full task ran with zero outbound network")


def latency() -> Result:
    adapter = _provider()
    ex = Executor(adapter)
    bar_ms = 50.0   # fixture bar; real EHR bar set from first baseline
    t0 = time.perf_counter()
    steps = 0
    for name, actions in TASKS.items():
        for a in actions:
            sky = adapter.capture(APP, WIN)
            ex.perform(a, sky)
            steps += 1
    per_step = (time.perf_counter() - t0) * 1000 / steps
    return Result("latency", f"{per_step:.2f} ms/step", per_step < bar_ms,
                  f"under {bar_ms:.0f} ms/step on the control case")


ALL = [perception, grounding, task_success, replay_determinism,
       heal_test, phi_containment, latency]


def agnostic_learn() -> Result:
    """Any driver can teach a flow through the same learn loop, model-agnostic.

    Uses the ScriptedDriver as a stand-in teacher. The learn loop never names a
    model; swapping in ClaudeDriver or CodexDriver changes only that one object.
    The recorded flow must then replay with no driver at all.
    """
    from engine.driver import ScriptedDriver, learn
    from engine.recorder import Recording, replay

    adapter = _provider()
    teacher = ScriptedDriver(TASKS["read_lab_result"])
    recorded = learn("read the latest lab result", teacher, Executor(adapter),
                     adapter, APP, WIN)
    rec = Recording("read_lab_result", APP, WIN, recorded)
    out = replay(rec, Executor(_provider()), _provider())
    ok = out == EXPECTED["read_lab_result"] and teacher.name == "scripted"
    return Result("agnostic_learn", f"taught by '{teacher.name}', replayed model-off",
                  ok, "any driver teaches; flow replays with no model")


ALL.append(agnostic_learn)
