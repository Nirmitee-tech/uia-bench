# Roadmap: best-in-class, from the Codex teardown

## Platform, then applications

This is a generic integration platform first. The core is domain-neutral:
capture, act, learn, replay, heal, flow-as-API, policy, trace, measure. Domain
features are applications on top, kept out of the core:

- Core (open, generic): everything in `engine/` and the suite.
- Application packs (on top): healthcare (FHIR mapping, PHI redaction, EHR flow
  libraries) is the first; finance, logistics, and others follow the same shape.

Keeping the core domain-neutral is a design rule: a healthcare term never enters
`engine/`. That is what makes the platform reusable and the open-source story
broad, with healthcare as the first commercial application rather than the scope.


Goal: the open-source computer-and-browser-use framework people reach for first.
This roadmap is derived from reverse-engineering Codex Computer Use (the shipped
JavaScript, its API docs, and the native binary), so every item is a real feature
Codex ships, matched or beaten in the open.

## What Codex ships (observed from its own API surface)

Its desktop API: list_apps, list_windows, launch_app, activate_window,
get_window_state, get_screenshot, click, move / move_to / move_relative, drag,
drag_handle, scroll, press_key, key_down / key_up, type_text,
perform_secondary_action, select_text, set_value, and clipboard
read / write / release. For browser tabs it uses element-index actions when an
accessibility element exists, screenshots and coordinates when they do not, and
Playwright locators for DOM-only tabs. It fuses the accessibility tree and a
screenshot in one capture (getAXStateAndScreenshot), diffs state between calls
to stay cheap, and runs a confirmations policy before risky or data-sharing
actions.

## Where we already match or beat it

- Full input control: move, click, right/double click, drag, scroll, type, key
  chords with modifiers, via real CGEvent. Done.
- Background delivery that does not steal focus (CGEventPostToPid). Codex drives
  the frontmost app; our background mode is a genuine addition.
- Model-agnostic teacher: OpenAI, Anthropic, local, vision, auto. Codex is tied
  to its own model. This is our edge.
- Record once, replay with no model, self-heal. Codex re-runs the model each time.
- A measurement suite (ten classes) and a PHI-containment proof. Codex ships
  neither to the user.
- DOM browser control over CDP, standard library only. Proven live: read 25
  patient rows and a name straight from the DOM of a real web EHR.
- The vision path for pixels-only screens (RDP/Citrix). Plumbing proven live.

## The gap, and how we close it

Ordered by value for UI-driven EHR integration.

1. DOM browser driver, finished (CDP). STATUS: core working (connect, navigate,
   read, click, type by selector). NEXT: expose it as a `Driver` so a model picks
   selectors, and add a DOM skyshot (interactive elements + roles) to teach from.
2. Fused capture: one skyshot carrying both the accessibility tree AND a
   screenshot, matching getAXStateAndScreenshot. Today element mode is text-only
   and vision mode is image-only. Fusing them lets a model see and read together
   on a dense EHR screen.
3. Complete the input API to Codex parity: clipboard read/write/release,
   move_relative, key_down/key_up as separate events, select_text, set_value.
   Most are small additions to the Swift `act` command.
4. State diffing between captures, so a step returns only what changed. This is
   the token-efficiency feature that makes long flows cheap.
5. An open, auditable action-risk policy and approval gate, modelled on Codex's
   confirmations policy but documented and extensible: classify an action
   (delete, transmit sensitive data, submit a form, bypass a safety barrier),
   require human confirmation, and write an audit record. For healthcare this is
   a differentiator, not a copy.
6. Real-target measurement: run the suite against OpenEMR (web), a sandbox EHR,
   and one RDP/Citrix window. Publish the numbers per target. This is what turns
   claims into evidence and the report into proof.

## Deliberately later

- Full headless mass-scale on macOS (session/VM per worker). Works via VMs now;
  native headless is a later effort.
- Linux and Windows adapters. The architecture already separates the adapter, so
  these are additive, not a rewrite.

## The bar

A user should be able to install this, point it at any app or web page, teach a
flow once with the model they already have, and replay it forever for free, with
numbers telling them how reliable it is on their screens, and patient data never
leaving the machine. Nothing open-source does all of that today. That is the bar.
