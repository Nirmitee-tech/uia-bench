# uia-bench

A test harness for UI-driven integration: driving an app the way a person does,
for systems that expose no API. Built by reverse-engineering the approach behind
Codex Computer Use, not its binary. The harness comes first, on purpose: it tells
us with numbers where the approach holds and where it breaks, before we build the
full system or point it at a real EHR.


## What this is

A generic integration platform: the API for software that has no API. Teach it
any application's screen once, and it exposes that workflow as a callable API. Any
system a person can operate -- a legacy ERP, a bank or insurer portal, a
government site, a logistics tool, a CRM, an old terminal app -- becomes
integrable, with no cooperation from the vendor.

The core is domain-neutral. It captures a screen, acts on it, learns a flow,
replays it with no model, heals it on change, exposes it as an API, and measures
its own reliability. Nothing in the core knows about any industry.

Domains are applications on top. Healthcare is the first: a pack that maps flow
output to FHIR and redacts patient data, with EHR flow libraries. Finance,
logistics, and others plug in the same way. Platform first, applications on top.

## 60-second quickstart

```bash
git clone https://github.com/Nirmitee-tech/uia-bench && cd uia-bench
swiftc -O native/skyshot/Skyshot.swift -o native/skyshot/skyshot   # macOS
python3 bench.py          # 14 test classes, should be green
python3 scan.py "Finder"  # read a live app's control tree
```

Teach a flow with any model, then replay it forever with no model:

```bash
export OPENAI_API_KEY=...            # or point UIA_LOCAL_BASE at a local model
python3 uia.py learn "Finder" "open Applications" --driver openai --out flow.json
python3 uia.py replay flow.json      # no model, deterministic
```

## Features at a glance

- Drive any app: see the control tree (accessibility), see pixels (vision), and
  act with the full mouse and keyboard, foreground or background.
- Drive any web page by its real DOM over Chrome DevTools Protocol. No browser
  framework dependency.
- Model-agnostic: OpenAI, Anthropic, a local model, vision, or auto. Swap freely.
- Learn once, replay with no model, self-heal when a screen changes.
- Open, auditable action-risk policy with a human-approval gate and an audit log.
- A run trace: every flow writes a JSON record and an HTML evidence report.
- A measurement suite: fourteen test classes, including a PHI-containment proof.
- Standard library only. MIT licensed.

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

## What is real today (no stubs)

- `native/skyshot/Skyshot.swift` reads a live AX tree AND performs real input via
  CGEvent (`act click|type|key`). Confirmed: typed text into TextEdit end to end.
- `engine/llm.py` is a real model client (stdlib only) speaking OpenAI-compatible
  chat and Anthropic messages. Point it at OpenAI, Codex, Anthropic, or a local
  server (Ollama/LM Studio/vLLM) by env. The reply parser refuses any control not
  on screen, so a model never clicks something that is not there.
- `engine/driver.py` makes the teacher swappable data, not code: openai /
  anthropic / local drivers share one contract. The learn loop never names a model.
- `uia.py` is the CLI: bench, scan, drivers, learn, replay.
- `bench.py` runs nine test classes green, including a real parser-guard test.

## Full input control and not disturbing your workflow

The executor drives any application's keyboard and mouse. Verbs: move, click,
rclick (right), dclick (double), drag, scroll, type, and key with modifier chords
(e.g. `a+cmd` for select-all, `Return`, `Tab`, arrows). All through real CGEvent.

Two delivery modes:

- Foreground (default): events go to the shared input stream and drive whatever
  is frontmost, exactly like a person. Simple and universal.
- Background (`MacosAdapter(background=True)`, CLI `--bg`): events are delivered
  to the target app's process with CGEventPostToPid. The app receives the input
  without the hardware cursor moving and without stealing your focus. Proven: text
  typed into a background TextEdit while Chrome stayed frontmost.

Honest limit on isolation: background mode avoids moving your cursor and taking
focus, and works for most Cocoa apps. It is not perfect isolation -- some apps
only accept input when active, and a shared global shortcut can still fire. For a
hard guarantee that automation never touches your live session, run the target in
a separate space: a second macOS user (launchctl asuser), a VM (UTM/Parallels),
or a virtual display. The framework runs the same in any of those. For an RDP or
Citrix EHR this is the recommended setup: the remote window lives in its own VM
or session, and the automation drives it there.

## DOM browser control (CDP)

For web apps, the framework talks to Chrome's DevTools Protocol directly, so it
acts on the page's real element tree rather than pixels -- the most reliable and
fastest web path, the open-source equal of what Codex does with Playwright. Proven
live: connected to a real web EHR, read 25 patient rows and a patient name straight
from the DOM. Standard library only.

Launch Chrome once with remote debugging, then use `engine/browser_cdp.py`:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9222 --user-data-dir=/tmp/uia-chrome
```

See ROADMAP.md for the full feature plan derived from the Codex teardown.

## The vision path (works without local elements)

For screens with no accessibility tree -- a remote desktop (RDP/Citrix), a canvas
app, a game -- there are no named controls. The framework captures the window as
an image and asks a vision model for a click coordinate, then clicks through the
same CGEvent executor.

- `engine/vision.py`: captures the window (screencapture + sips), normalises the
  image to point size so pixels map 1:1 to screen points, calls a vision model,
  and maps the returned pixel to a global screen point. Proven live: a 1512x982
  window captured and normalised; coordinate math covered by the vision_parse test.
- `AutoDriver` fuses both: it uses element grounding when the tree is present and
  the vision path when it is empty. One driver reaches a native app AND a remote
  desktop. Drivers: openai, anthropic, local, vision, auto.

This is the piece that lets the system drive an RDP/Citrix EHR, where no API and
no accessibility tree exist. It needs a vision-capable model (OpenAI-compatible,
or a local one via UIA_LOCAL_BASE to keep PHI on the machine).

## Still to come

- A captured ScreenCaptureKit frame alongside the tree (vision-only path).
- Model-driven heal for genuinely ambiguous cases (today's healer is heuristic).

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
