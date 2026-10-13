# Measuring computer use for UI-driven integration

## Why this exists

Most healthcare systems a client needs to connect to expose no API. Legacy EHRs,
thick clients, and portals give you only the screen a human uses. The way in is
to drive that screen: read it, click it, type into it, the way a person does.

This is a real engineering discipline, not a trick. It used to be called RPA
(robotic process automation: scripted bots clicking fixed coordinates), and it
broke on every screen change. A model that reads the screen can adapt, which is
what makes it durable enough to sell. But "durable" is a claim, and a claim
without measurement is marketing.

So we built the measurement first. You cannot fix what you cannot measure. This
harness tells us, with numbers, where screen automation holds and where it
breaks, before we build the full system or point it at a live EHR.

## The goal

One sentence: prove, with repeatable numbers, how reliably a model can operate a
real application through its screen, and keep that proof honest about its limits.

Everything here serves that goal. The harness is not the product. The product is
a self-repairing library of integration flows. The harness is how we know the
product works, on each new system, before we promise anything to a client.

## What we measure

A model operating a screen can fail in seven distinct ways. We measure each one
on its own, so a failure points at a cause instead of a vague "it didn't work."

| What we measure | The question it answers | Why it matters |
|---|---|---|
| Perception | Did the system see the control at all? | If it can't see it, nothing downstream works |
| Grounding | Did it act on the right control, not a neighbor? | The difference between correct and dangerous |
| Task success | Did the whole task finish, end to end? | What the client actually cares about |
| Replay determinism | Does the recorded flow repeat with no model? | The cheap, fast production path |
| Heal | When a screen changes, does the flow recover? | Whether it survives real-world churn |
| PHI containment | Did any patient data leave the machine? | The compliance line, made testable |
| Latency | Is it fast enough to be useful? | A correct bot nobody waits for is useless |

Perception and grounding are the two words worth keeping. Perception is whether
the system can see a control. Grounding is whether it turns "click the Labs
button" into the one correct control instead of a nearby one. Most real-world
failures live in these two, which is why we score them separately from task
success.

## What the results tell a reader

The harness runs green on a controlled case, which means the measurement itself
is sound: the seven classes agree with a screen whose right answers we know. That
is the baseline every real system gets compared against.

The first real-world signal is coverage: on a live application the skyshot (the
fused screenshot plus the control tree) reads the accessibility tree directly.
Where that tree is rich, the model clicks named controls and reliability is high.
Where it is sparse, the model falls back to reading pixels, and reliability drops.
Triaging each target into rich or sparse is the first decision the numbers drive.

## What this is honest about

Measurement earns trust only if it states its own limits.

- The controlled case is deterministic by design. Its perfect scores prove the
  harness is correct, not that any real system is perfect. Real targets get real
  numbers, set from their first measured baseline.
- Reading a live screen is proven. Acting on a live screen is deliberately held
  back until a target clears the perception and grounding bars. We do not operate
  a live system until the numbers show we see it correctly.
- The containment check proves our own code sent nothing over the network during
  a task. It is not an operating-system firewall. A production deployment still
  needs an OS-level network block, and the report says so rather than implying
  the check is more than it is.
- The hardest targets, thick clients delivered over remote desktop, have unknown
  numbers until we scan one. That unknown is the point of building the harness.

## What a client is accountable for

The client owns HIPAA and GDPR sign-off (the US and EU rules for handling
personal and health data). This harness exists so that sign-off rests on measured
behavior, not a vendor's word. The local-first design keeps patient data on the
client's machine, and the containment measurement is the evidence behind that
claim.

## The shape of the work ahead

1. Scan each target system and record its coverage number. This decides which
   are reliable today and which need the harder vision path.
2. For a cleared target, wire live action behind its perception and grounding
   numbers, then measure task success and latency on real tasks.
3. Record each proven task as a flow, confirm it replays with no model, and
   confirm it heals when the screen changes.
4. Publish the measured numbers per target, with the limits stated, as the proof
   behind every integration we offer.

The order is the discipline. We measure, then we build, then we promise. Not the
other way around.
