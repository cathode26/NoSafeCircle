# Can we run many more game tasks at once? Measured 2026-09-17

Vincent: *"I want to consider maybe we need to refactor components if we are working on too much shared code? I want to consider if we have plenty of work already we just need to use the multi threading and do more tasks? Lets turn this up."*

Computed from the 95 committed contracts and `taskcontrol states`, plus the Pipeline Maintainer's machine measurements. Read-only; nothing was changed.

## The short answer

**Refactoring is not what is stopping us today, and yes, there is plenty of ready work.** Eight tasks could run right now without any two touching the same file. What stops us reaching eight is one provider account, 15 GB of free memory and one Unity — not shared code.

**But shared code is the ceiling for the wave after this one**, and it is worth contracting the fix before we get there rather than after.

## What the graph actually says

| Measure | Count |
|---|---|
| Active implementation tasks | 75 |
| Still to do | 58 |
| Minus `aggregate` and `needs_replan` (not dispatchable shapes) | −7 |
| **Dependencies satisfied, could start now** | **15** |
| Blocked on dependencies | 36 |
| Of the 15: could run **concurrently**, no shared file | **8** |
| Of the 15: conflict with nothing at all | 6 |

The eight that can run together: NSC-007, NSC-043, NSC-044, NSC-061, NSC-064, NSC-065, NSC-085, NSC-091.

**Corrected 2026-09-17 (Game Agent).** My first pass counted 19 ready and 9 concurrent because it filtered only on
dependency state. Three of those — NSC-020 (`needs_replan`), NSC-026 and NSC-057 (`aggregate`) — are not dispatchable
work at all. **Filter cheapest-first:** (1) `derived_state` and `kind`, free; (2) file presence against HEAD, cheap;
(3) run the gate, decisive. Tier 1 alone disqualified three, and tier 2 caught NSC-061 as unstarted work rather than
missing paperwork — its two claimed files do not exist.

## The real constraint is the dependency wall, not contention

36 dispatchable-shaped tasks are blocked, and **102 of their 119 blocking links point at tasks in `not_delivered`**. Only 17 tasks of 95 are `conformant`. So the graph is not short of work — it is short of *finished, recorded* work.

Six tasks gate most of it:

| Blocker | Gates | State |
|---|---|---|
| NSC-092 Enemy NavMesh pursuit, search, door traversal | 8 | not_delivered |
| NSC-013 Enemy status-effect and forced displacement | 7 | not_delivered |
| NSC-089 NavMesh surface and enemy agent configuration | 7 | not_delivered |
| NSC-091 Enemy target detection and search state | 7 | not_delivered |
| NSC-050 DoorInteractable auto-lock, durability, breaking | 5 | not_delivered |
| NSC-078 PixelLab dungeon prop and architecture PNGs | 5 | not_delivered |

Four of the six are one chain: **NSC-089 → NSC-091 → NSC-092 → NSC-013**, the enemy AI spine. Finishing that chain converts roughly 22 blocking links, far more than any refactor would.

## Where shared code does bite

Across the 58 remaining tasks, **41 touch a file some other task also claims**. Two files dominate:

| Claimed by | File |
|---|---|
| **23 tasks** | `Assets/Scenes/DoorPrototype.unity` |
| **19 tasks** | `Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs` |
| 9 tasks | `Editor/World/DoorPrototypeGlobalSceneBuilder.cs` |
| 7 tasks | `logical:enemy-locomotion-behavior-surface` |
| 5 each | `RoomSceneCatalog.cs` / `.asset`, `DoorInteractable.cs`, `TitleScreenController.cs` |

One scene and one builder are claimed by a third of the backlog. Today that is survivable because most of those 23 are *blocked anyway*. The moment the enemy chain lands and those tasks become eligible, the scene and the builder become the serialisation point.

**The refactor worth contracting**, when we choose to: split the monolithic `DoorPrototype.unity` into additive sub-scenes, and `DoorPrototypeSceneBuilder.cs` into per-area builder units, so a task claims its slice instead of the whole. That is a real engineering task with test implications — GER's to contract, not something to do ad hoc mid-crew.

## The machine ceiling (Pipeline Maintainer, measured tonight)

- **One provider account** is the hard ceiling: every crew, decomposition and helper job spends `cathode26@gmail.com`. Eight crews is ~24 role calls plus reviews on one account.
- **Memory is thinner than it looks:** 22 logical CPUs, 63 GB total, **15 GB free**, Docker capped at 31 GB. Four concurrent heavy jobs already starved a test into a 30-minute timeout that passed in seconds when idle.
- **Main writes serialise** — integration, apply-decomposition and contract commits share the one canonical checkout. Crews clone, so they don't contend; the reconciliation at the end does.
- **Unity is strictly one at a time**, and it is the narrowest funnel for anything needing delivery evidence.
- Session pools are *not* the limit: capacity 40, 13 concurrent runs with three crew roles.

## What to do, in order

1. **Turn it up, but the number is conditional, not flat.** The Game Agent's read: **2-3 concurrent while Unity is also running**, because Unity is serial and competes for the same machine; **4 is defensible on a day with no Unity run**, since crews are Docker. Nobody has sampled a crew's peak memory yet - the Game Agent will on the NSC-007 retry, and that number should set the ceiling.
2. **Point the first wave at the enemy chain** (NSC-089, then 091, 092, 013). It is the single biggest unblocker, and NSC-091 is already in the run-now set.
3. **Clear evidence debt in parallel** — it is free throughput. Merged work that was never recorded keeps its dependents blocked for no engineering reason.
4. **Decide on a second provider account.** That is the one lever that raises the true ceiling; refactoring does not.
5. **Contract the scene/builder split** before the post-unblock wave, not during it.

## Caveats

- "Could run concurrently" is a greedy lower bound on the independent set; the true maximum may be slightly higher.
- **"Ready" is two different things.** Some tasks need a *crew* (code absent); others need only an *evidence pass* (code merged, record missing). A file-presence sweep against HEAD found 10 candidates with every claimed file already on main; after the state filter the clean evidence queue is **NSC-089 and NSC-091** (no Vincent time), then **NSC-044, NSC-045, NSC-048**, whose gates need him personally and batch into one sitting. Dispatching a crew at an evidence pass burns a run and can reimplement working code.
- `exclusive_resources` is a *declaration*. A contract claiming a whole folder serialises more than one claiming the file it edits, so some contention may be declaration style rather than real coupling — the GER Agent is the judge of that.
- No crew's peak memory has been measured yet. Every concurrency number above 4 is inference until it is.
