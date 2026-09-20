# Recording script — No Safe Circle, 2026-09-17

Four acts, in your order: say what's broken → run the tasks → watch the viewer → open Unity and test.
Every number below is measured tonight, not estimated. Where something might not work on camera, it says so.

---

## ACT 1 — What we're fixing (record before dispatch)

### Shot 1: the bug reel, no commentary

- Fire the fireball through a wall.
- Fire it through a closed door.
- Stand behind a closed door and let the enemy see you through it.

**These expire the moment the fixes land. Shoot them first.**

### Shot 2: "Here's the fireball bug, and why it isn't a bug"

> "The fireball goes through walls. But it isn't broken — it was never built. What you're casting right now is a demo stub buried in the run flow, and it does **no collision test at all**. Nothing stops it because nothing was ever asked to."

**The task:** NSC-007 deletes that stub, builds `Fireball.cs` and `FireballProjectile.cs`, and requires that walls, props and any closed door stop the projectile — tested every tick with a chest-height raycast.

### Shot 3: "Here's the door bug, and this one is real"

> "The enemy sees me through a closed door. It isn't the AI — the sight check is correct. It's that the door doesn't fill its own doorway."

**The measurement, on screen if you want it:**

```
blocker collider : 2 units wide, centred
the wall opening : 3 units
x offset ±1.0    → hits the door
x offset ±1.25   → NOTHING. Open sightline.
```

**A half-unit slit down each jamb. Ten open slots across five doors.**

> "And the cause is one line, with a comment that explains the mistake."

`DoorPrototypeSceneBuilder.cs:1088` — `size = (2, 2.5, 0.3)` under a comment reading *"sized to the door's footprint"*.

> "The collision was sized to the door **art** instead of to the hole in the wall."

### Shot 4: say the honest thing about scope

> "Fixing the fireball does **not** fix doors. Its new raycast will find the same real gap — it can pass every test and still fly straight through. Two separate fixes, and I'd rather say that now than have you spot it."

---

## ACT 2 — Run the tasks

### Shot 5: the dispatch

NSC-007 is already **prepared** — that's the state before a worker starts. Dispatch on camera.

> "This spins up a disposable clone and a container. Three roles work the contract: one implements, one reviews, one checks it against the acceptance criteria. I'm not writing the code — I'm approving what comes back."

**Expect 30–40 minutes.** The previous attempt ran 36 before a role timeout.

### Shot 6: what to say while it runs

- **The contract is the unit of work, not the ticket.** NSC-007 has acceptance criteria precise enough that a machine can fail them.
- **`exclusive_resources` is why several can run at once** — two tasks that claim the same file can't be dispatched together.
- **The honest number:** 15 tasks are dispatchable right now, 8 could run at once without touching the same file. What stops us going wider isn't the machine — it's one provider account and one Unity.
- **The real bottleneck is paperwork, not code:** only 17 of 95 tasks are recorded conformant, and **27 tasks are blocked solely by dependencies whose code is already on main but has no delivery record** - roughly **1.6x the entire pool of work eligible to start.**
- **And contention is not the problem people assume:** among the eligible tasks only **20 of 136 pairs** claim the same file. **86% could run side by side today.** What limits us is one provider account and one Unity, not shared code.

---

## ACT 3 — The live viewer

### Shot 7: narrate the states

> "Prepared. Reserved. Working. Candidate. Integrated."

- **Prepared** — contract validated, nothing running.
- **Reserved** — resources claimed; no other task can touch those files.
- **Working** — the crew is in the clone.
- **Candidate** — work exists but has touched nothing real yet.
- **Integrated** — it's on main.

> "Nothing reaches the game until a candidate survives review. That gap is the whole point."

---

## ACT 4 — Open Unity and test

**Test in this order. Expected results are what should happen if the fix landed.**

| Test | Do this | Pass looks like |
|---|---|---|
| **Fireball vs wall** | Cast at a solid wall | Stops at the wall |
| **Fireball vs closed door** | Cast at a closed door | Stops — **only if the door fix landed too.** If it still passes through, that's the jamb seam, not NSC-007 failing |
| **Fireball charge** | Hold, then release | Charge builds, costs mana, releases as a stronger cast |
| **Door sightline** | Stand behind a closed door, off-centre | Enemy does **not** react — after the seam fix |
| **Enemy pursuit** | Let one see you, then break line of sight | It chases, then searches your **last known position** |
| **Ruined Entry** | Walk the room | A built room, not the prototype box |

### Say these out loud if they happen — they're true and they're cheap to explain

- **Enemy attacks look wrong:** there is **no attack art**. Idle and a six-frame walk per facing, nothing else. An attack plays a walk or idle pose.
- **The wizard looks the wrong size:** `ImportWizardSprite` still uses PPU 180 from the old 180 px art. Against today's 128 px art he renders at **0.58 units** — less than half an enemy. NSC-096 fixes it.
- **The wizard doesn't fit the doorway:** the opening measures **1.00 × 1.30 world units** against a **1.64-unit** wizard. Either the door sprite binds at ×1.54 or the art gets more passage and less arch. Undecided on purpose.

---

## What not to claim on camera

- **Don't say three tasks fix three bugs.** NSC-007 is a real fix. NSC-091 and NSC-044 are **already built** — they need a Unity run and a record, not a crew. Saying otherwise falls apart the moment you test main.
- **Don't credit NSC-007 with doors.**
- **Don't promise the enemy art is new** — it's been in the game; it just never had its records.

## The better story, if you want one line for the top

> "Most of what's missing in this game isn't code. It's proof that the code works. Tonight you'll watch one task get built, and three that were already finished get their paperwork — and that's the thing actually holding the project back."
