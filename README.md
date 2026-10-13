# uia-bench

A test harness for UI-driven integration: driving an app the way a person does,
for systems that expose no API. Built by reverse-engineering the approach behind
Codex Computer Use, not its binary. The harness comes first, on purpose: it tells
us with numbers where the approach holds and where it breaks, before we build the
full system or point it at a real EHR.

## Why this exists

Most healthcare value sits behind systems with no API: legacy EHRs, thick
clients, state portals. The only door is the screen a human uses. The effective
trick, confirmed from the teardown, is the **skyshot**: a screenshot fused with
the accessibility tree (the OS's named list of on-screen controls), every control
given a stable index. A model clicks "the Labs button," not a guessed pixel.

Because actions anchor on element identity (role + label), a flow recorded once
replays with no model. The model returns only to repair a flow when a screen
changes. That record / replay / heal loop is the production path and the moat.

## What is real today

- `native/skyshot/Skyshot.swift` — compiles and runs. It walks `AXUIElement` on a
  live window and emits the control tree as JSON. Confirmed against Finder: 81
  controls, 22 actionable. This is the real skyshot, read-only.
- `bench.py` — the seven test classes run green on a deterministic fixture.
- `scan.py` — runs perception against any live Mac app and reports AX coverage.

## What is not wired yet (stated honestly)

- Action apply on a live app (CGEvent clicks/keystrokes). The macOS adapter can
  SEE a window, not yet ACT on it. Gated behind real-app perception/grounding
  numbers: we do not click a live app until the suite shows we see it correctly.
- A captured ScreenCaptureKit frame alongside the tree.
- The model-driven learn phase and the model call for ambiguous heals.

## The seven test classes and their bars

| Class | Checks | Bar (fixture control case) |
|---|---|---|
| perception | skyshot lists the target control | 100% recall of gold labels |
| grounding | resolves the right control, not a neighbor | 100% |
| task_success | 3 read-only tasks end to end | 20/20 runs |
| replay_determinism | record once, replay model-off | 20/20 identical |
| heal | rename a control, auto re-resolve and re-save | recovers |
| phi_containment | full task runs with zero outbound network | 0 egress |
| latency | time per step | < 50 ms/step |

Fixture bars are strict because the fixture is deterministic. Real EHR bars get
set from the first measured baseline, not guessed.

## Run it

```bash
python3 bench.py                 # the suite, green on the fixture
swiftc -O native/skyshot/Skyshot.swift -o native/skyshot/skyshot
python3 scan.py "Finder"         # AX coverage of a live app
```

Needs Node-free Python 3.9+, and macOS Accessibility permission for the caller
(System Settings > Privacy & Security > Accessibility) to scan a live app.

## Compliance boundary

The `phi_containment` class proves the harness made no network call during a
task, so the local-first claim is testable, not a promise. It is not a kernel
firewall; a production deployment still needs an OS-level egress block. The test
documents that boundary rather than overclaiming. The customer owns HIPAA and
GDPR sign-off; this harness exists so that sign-off rests on measured behavior.

## Layout

```
bench.py              suite runner, exit 0 only if every class passes
scan.py               live-app AX coverage probe (read-only)
engine/
  skyshot.py          Skyshot + Element (identity = role::label)
  actions.py          Action model + Executor (identity-first, pixel fallback)
  recorder.py         record once, replay model-off, stability check
  healer.py           re-resolve a broken target and rewrite the recording
  adapters/
    fixture.py        deterministic in-memory app (the control case)
    macos.py          live skyshots via the Swift CLI; action apply stubbed
tests/
  suite.py            the seven classes and their pass bars
  gold/               hand-labeled gold screens (masked, synthetic)
sandbox/
  egress_guard.py     blocks + records outbound network for the PHI test
native/skyshot/       Swift AX dumper (compiles to ./skyshot)
```
