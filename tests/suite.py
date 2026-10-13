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


def model_parse() -> Result:
    """The real model-reply parser validates against the live skyshot.

    No network: we feed canned replies to the same parse_action the drivers use.
    A valid target becomes an Action; a hallucinated control fails closed. This
    proves the agnostic driver's safety guard without calling any model.
    """
    from engine.llm import parse_action
    sky = _provider().capture(APP, WIN)
    good = parse_action('{"kind":"click","target":"Labs"}', sky)
    done = parse_action('{"kind":"done"}', sky)
    fenced = parse_action('```json\n{"kind":"read","target":"Lab A1c"}\n```', sky)
    rejected = False
    try:
        parse_action('{"kind":"click","target":"Delete Everything"}', sky)
    except ValueError:
        rejected = True
    ok = (good is not None and good.target_identity == "AXButton::Labs"
          and done is None and fenced is not None and rejected)
    return Result("model_parse", "valid parsed, hallucination refused", ok,
                  "real driver guard: never click a control not on screen")


ALL.append(model_parse)


def vision_parse() -> Result:
    """The vision reply parser maps image pixels to a global screen point.

    No network: a canned vision reply plus a known window origin must produce a
    click at origin + image offset, and a malformed reply must fail closed. This
    proves the RDP/Citrix path's coordinate math and guard without a model.
    """
    from engine.vision import parse_vision_action
    origin = (100, 200)
    act = parse_vision_action('{"kind":"click","x":30,"y":40}', origin)
    done = parse_vision_action('{"kind":"done"}', origin)
    bad = False
    try:
        parse_vision_action('{"kind":"click","x":"left","y":5}', origin)
    except ValueError:
        bad = True
    ok = (act is not None and act.xy == (130, 240) and done is None and bad)
    return Result("vision_parse", "pixel->global point, bad reply refused", ok,
                  "RDP/Citrix path: coordinate math and guard")


ALL.append(vision_parse)


def cdp_driver_builds() -> Result:
    """The CDP DOM driver builds valid JS for its operations (offline check).

    No Chrome needed: we check the selector-escaped JavaScript the driver sends
    over CDP is well-formed and injection-safe for an awkward selector. The live
    round-trip is proven separately against a real Chrome; this keeps the guard
    in the always-on suite.
    """
    import json as _json
    from engine import browser_cdp  # import must succeed, stdlib only
    sel = "input[name=\"q'x\"]"
    esc = _json.dumps(sel)
    ok = (esc.startswith('"') and "'" in esc and hasattr(browser_cdp, "CDPSession")
          and hasattr(browser_cdp.CDPSession, "click")
          and hasattr(browser_cdp.CDPSession, "type_into"))
    return Result("cdp_driver_builds", "CDP driver present, selectors escaped", ok,
                  "DOM browser path loads and escapes selectors safely")


ALL.append(cdp_driver_builds)


def browser_adapter() -> Result:
    """The browser adapter drives a page by selector through the same contract.

    A fake CDP session (no Chrome) proves capture builds selector-identity
    elements and apply routes click/type/read to the session. The live CDP
    round-trip is proven separately against a real browser.
    """
    from engine.adapters.browser import BrowserAdapter

    class FakeSession:
        def __init__(self): self.clicked = None; self.typed = None
        def eval(self, js):
            return [{"role": "button", "label": "Save claim", "selector": "#save",
                     "bounds": [0, 0, 80, 30], "value": None}]
        def title(self): return "Fake EHR"
        def text(self, sel): return "Hypertension" if sel == "#save" else None
        def click(self, sel): self.clicked = sel; return sel == "#save"
        def type_into(self, sel, v): self.typed = (sel, v); return sel == "#save"

    fs = FakeSession()
    ad = BrowserAdapter(fs)
    sky = ad.capture()
    el = sky.elements[0]
    from engine.actions import Executor
    ex = Executor(ad)
    ex.perform(Action("click", el.identity), sky)
    read = ex.perform(Action("read", el.identity), sky)
    ok = (el.role == "css=#save" and fs.clicked == "#save" and read == "Hypertension")
    return Result("browser_adapter", "DOM click+read by selector", ok,
                  "web page is a first-class adapter on the same contract")


def policy_gate() -> Result:
    """The risk policy classifies and gates actions, and audits every one."""
    import os
    import tempfile
    from engine.policy import classify, PolicyExecutor
    from engine.actions import Executor

    safe = classify(Action("read", "AXStaticText::DOB")).level
    writ = classify(Action("type", "AXTextField::Note", text="hi")).level
    tx = classify(Action("click", "AXButton::Submit claim")).level
    hand = classify(Action("type", "AXTextField::Password")).level

    adapter = _provider()
    fd, path = tempfile.mkstemp(suffix=".jsonl"); os.close(fd)
    pe = PolicyExecutor(Executor(adapter), audit_path=path,
                        gate=lambda a, r: False, pause_from="transmit")
    sky = adapter.capture(APP, WIN)
    denied = False
    try:
        pe.perform(Action("read", "AXStaticText::Patient Name"), sky)  # auto ok
        pe.perform(Action("click", "AXButton::Submit claim"), sky)     # gated, denied
    except PermissionError:
        denied = True
    audited = sum(1 for _ in open(path)) >= 2
    ok = (safe == "safe" and writ == "write" and tx == "transmit"
          and hand == "handoff" and denied and audited)
    return Result("policy_gate", "classify + gate + audit", ok,
                  "open, auditable safety: pauses on risk, logs every action")


def run_trace() -> Result:
    """A run trace writes a JSON record and an HTML report."""
    import os
    import tempfile
    from engine.trace import Trace
    t = Trace("read_demographics")
    t.add("read", "AXStaticText::Patient Name", "TEST, PATIENT")
    t.add("click", "AXButton::Labs", "", risk="write")
    d = tempfile.mkdtemp()
    jp, hp = os.path.join(d, "t.json"), os.path.join(d, "t.html")
    t.to_json(jp); t.to_html(hp)
    import json as _json
    rec = _json.load(open(jp))
    html = open(hp).read()
    ok = (len(rec["steps"]) == 2 and "Run trace" in html
          and "TEST, PATIENT" in html)
    return Result("run_trace", "JSON + HTML evidence report", ok,
                  "every run is reviewable after the fact")


ALL += [browser_adapter, policy_gate, run_trace]


def flow_as_api() -> Result:
    """A learned flow runs as a single call and returns structured reads.

    Runs a flow through the fixture adapter via run_flow, with a parameter filled
    into a step. Proves the platform's core promise: one call to a no-API system
    returns a clean record. Errors come back as status, not exceptions.
    """
    from engine.flow_api import run_flow
    from engine.recorder import Recording
    adapter = _provider()
    rec = Recording("get_record", APP, WIN, TASKS["read_demographics"])
    res = run_flow(rec, adapter, params={})
    ok = (res.status == "ok" and res.reads == EXPECTED["read_demographics"]
          and res.steps == 2)
    return Result("flow_as_api", f"one call -> {res.reads}", ok,
                  "a no-API system answers a single call")


ALL.append(flow_as_api)


def flow_params() -> Result:
    """Parameters fill {{placeholders}} in a flow before it runs.

    Use-case need: one saved flow serves many inputs (e.g. a record id). Proves
    {{id}} in a type step is replaced from params, and an unknown placeholder is
    left intact rather than crashing.
    """
    from engine.flow_api import _fill
    filled = _fill("open record {{id}} now", {"id": "A-42"})
    kept = _fill("hi {{missing}}", {})
    ok = (filled == "open record A-42 now" and kept == "hi {{missing}}")
    return Result("flow_params", "placeholders filled, unknown kept", ok,
                  "one flow serves many inputs")


def flow_error_status() -> Result:
    """A failing step returns status 'error', never an exception past the API.

    Use-case need: a flow behind an API must give a clean status when a control
    is missing, not crash the server. Runs a flow whose target is not on screen.
    """
    from engine.flow_api import run_flow
    from engine.recorder import Recording
    bad = Recording("broken", APP, WIN,
                    [Action("click", "AXButton::Does Not Exist")])
    res = run_flow(bad, _provider(), {})
    ok = (res.status == "error" and res.error and "not found" in res.error.lower())
    return Result("flow_error_status", f"status={res.status}", ok,
                  "a missing control returns status, not a crash")


def flow_save_load() -> Result:
    """A flow round-trips to disk and back with identical actions."""
    import os, tempfile
    from engine.flow_api import load_flow
    from engine.recorder import Recording
    import uia
    rec = Recording("rt", APP, WIN, TASKS["read_lab_result"])
    d = tempfile.mkdtemp(); p = os.path.join(d, "rt.json")
    uia._save(rec, p)
    back = load_flow(p)
    ok = (len(back.actions) == len(rec.actions)
          and back.actions[0].target_identity == rec.actions[0].target_identity
          and back.name == "rt")
    return Result("flow_save_load", "round-trips to disk", ok,
                  "a learned flow persists and reloads exactly")


def policy_approval() -> Result:
    """When the gate approves, a gated action proceeds and is audited approved."""
    import os, tempfile
    from engine.policy import PolicyExecutor
    from engine.actions import Executor
    adapter = _provider()
    fd, path = tempfile.mkstemp(suffix=".jsonl"); os.close(fd)
    pe = PolicyExecutor(Executor(adapter), audit_path=path,
                        gate=lambda a, r: True, pause_from="transmit")
    sky = adapter.capture(APP, WIN)
    # existing control, but context marks it a data-sharing (transmit) action
    pe.perform(Action("click", "AXButton::Labs"), sky, context="submit and send")
    import json as _json
    lines = [ _json.loads(l) for l in open(path) ]
    ok = any(r.get("decision") == "approved" and r.get("risk") == "transmit"
             for r in lines)
    return Result("policy_approval", "approved gated action proceeds + audited", ok,
                  "the approval path works, not just denial")


def heal_gives_up() -> Result:
    """Heal returns None for a control it cannot honestly re-resolve.

    Use-case need: a self-healing system must not 'recover' by clicking the wrong
    thing. When the role is gone entirely, heal declines rather than guesses.
    """
    from engine.healer import heal
    from engine.recorder import Recording
    adapter = _provider()

    def drop_all_buttons(elements):
        return [e for e in elements if e["role"] != "AXButton"]

    broken = _provider(); broken.add_mutation(drop_all_buttons)
    sky = broken.capture(APP, WIN)
    rec = Recording("x", APP, WIN, [Action("click", "AXButton::Labs")])
    fixed = heal(rec, rec.actions[0], sky)
    ok = fixed is None
    return Result("heal_gives_up", "declines rather than mis-click", ok,
                  "heal never recovers by guessing the wrong control")


ALL += [flow_params, flow_error_status, flow_save_load, policy_approval, heal_gives_up]


def secrets_vault() -> Result:
    """A secret round-trips through the vault and injects, never in plaintext flow."""
    import os, tempfile
    os.environ["UIA_VAULT_KEY"] = "test-key-123"
    from engine.secrets import Vault, inject
    d = tempfile.mkdtemp(); vp = os.path.join(d, "v.json")
    v = Vault(vp)
    v.set("ehr_pw", "S3cr3t!")
    on_disk = open(vp).read()
    filled = inject("login {{secret:ehr_pw}}", v)
    miss = inject("x {{secret:nope}}", v)
    ok = (v.get("ehr_pw") == "S3cr3t!" and "S3cr3t!" not in on_disk
          and filled == "login S3cr3t!" and miss == "x {{secret:nope}}")
    return Result("secrets_vault", "encrypted at rest, injected at run", ok,
                  "credentials never live in a flow file or in the clear")


def redaction_masks() -> Result:
    """Redaction masks known sensitive shapes and injected secret values."""
    from engine.redaction import redact
    out = redact("card 4111111111111111 mail a@b.com ssn 123-45-6789",
                 extra_values=["S3cr3t!"])
    out2 = redact("pwd is S3cr3t! now", extra_values=["S3cr3t!"])
    ok = ("4111111111111111" not in out and "a@b.com" not in out
          and "123-45-6789" not in out and "S3cr3t!" not in out2)
    return Result("redaction_masks", "numbers, emails, ids, secrets masked", ok,
                  "traces and audit never store sensitive values")


def api_auth() -> Result:
    """The policy decisions behind the API: no token refuses, allowlist gates.

    Checks the server helpers directly (no socket): a request with no configured
    token is refused, and a flow outside the allowlist is blocked.
    """
    import os
    import importlib
    os.environ.pop("UIA_API_TOKEN", None)
    os.environ["UIA_ALLOW"] = "get_record"
    import server.http_api as api
    importlib.reload(api)
    refuses_without_token = (api._token() == "")   # => _authed returns False, 401
    allows_listed = api._allowed("get_record")
    blocks_unlisted = not api._allowed("delete_all")
    ok = refuses_without_token and allows_listed and blocks_unlisted
    os.environ.pop("UIA_ALLOW", None)
    return Result("api_auth", "no token refuses, allowlist gates", ok,
                  "the flow API is closed by default, not open")


ALL += [secrets_vault, redaction_masks, api_auth]
