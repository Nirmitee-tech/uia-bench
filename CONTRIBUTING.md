# Contributing

Thanks for helping build the open-source standard for UI-driven integration.

## Ground rules

- Every change ships with a test in `tests/suite.py`, added to `ALL`. The bench
  must stay green (`python3 bench.py`, exit 0). CI runs it on macOS.
- Standard library only in `engine/`. No third-party runtime dependency. This
  keeps the framework trivially installable, which is the point.
- Honesty in comments and docs: separate what is measured from what is inferred,
  say what a check actually catches, and never imply static analysis observed a
  live run. See the house style in the commit history.
- New input or capture features extend the adapter interface, not the call sites,
  so drivers, record/replay, heal, and the suite keep working unchanged.

## Adding a driver (a new teacher model)

Implement one method: `next_action(goal, skyshot, history) -> Action | None`.
Register it in `engine/driver.py` `DRIVERS`. See `ModelDriver` and `VisionDriver`.

## Adding a target (a new kind of app)

Implement an adapter with `capture()` and `apply()` returning/consuming the same
`Skyshot`/`Element`/`Action` types. See `engine/adapters/` for macOS, fixture,
and browser examples.
