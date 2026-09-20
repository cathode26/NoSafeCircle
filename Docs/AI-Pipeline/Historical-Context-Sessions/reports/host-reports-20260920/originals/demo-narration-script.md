# No Safe Circle — Gauntlet Demo Narration

Nine tasks on screen. Two are real work from the actual game. Seven are synthetic
tasks that exist only to prove the pipeline handles a dependency graph.

---

## BEAT 1 — Opening (before you start the run)

> "This is the task graph for No Safe Circle. Every node is a contract — a task with
> acceptance criteria, file ownership, and dependencies. Nothing here is a prompt I
> typed. The graph is the source of truth, and it's validated: the hierarchy has to be
> connected and acyclic, and no two tasks can own the same file without an explicit
> shared-resource group."

Point at the nine nodes. All purple — **Task Unstarted**.

> "Two of these are real. NSC-200 is a genuine bug in the game: the wall tiles don't
> join seamlessly, so long walls show a repeating seam. NSC-201 is a task that's too
> big to implement directly — it has to be split first. The other seven are synthetic
> tasks that write small files and prove themselves with Unity tests."

---

## BEAT 2 — Show the bug first (Unity, before or after starting)

Open `Assets/Scenes/DoorPrototype.unity`.

> "Here's the bug the pipeline is about to fix. Look along the wall — the brick pattern
> resets. That's two defects compounding: the tile is generated at the wrong block
> width, and the code that decides whether to regenerate a stale tile only compares
> image dimensions, never the pixels. So once a bad tile is saved, it survives forever."

---

## BEAT 3 — Start the run

> "I'm starting the controller now. It isn't running a script — it reads the graph,
> works out which tasks are actionable, and dispatches them. Watch the states change."

Expect within the first minute:
- **NSC-200** → preparing an isolated checkout
- **NSC-201** → decomposition starts
- **NSC-1101, 1103, 1104, 1105** → prepare in parallel
- **NSC-1107, 1108, 1110** stay grey — dependencies unmet

> "Notice 1107, 1108 and 1110 aren't moving. They're waiting on their dependencies.
> The controller won't touch a task whose predecessors aren't done — that's enforced,
> not hoped for."

---

## BEAT 4 — The decomposition (the interesting part, ~8 minutes)

> "NSC-201 is doing something different. It's too large for one agent, so it's being
> decomposed — and this is two-provider work. One model proposes the split; a second,
> independent model reviews it. If the reviewer rejects it, the author gets exactly one
> bounded correction round, then it either passes or it stops."

> "The proposal is review-only. Nothing touches the graph until a human approves the
> exact plan. That's deliberate — an agent can propose a change to the task graph, but
> it can't apply one."

---

## BEAT 5 — Crews and tests

> "Each task that gets dispatched runs in its own isolated checkout with its own branch.
> A crew works it — implementer, test author, validator — and the result is only accepted
> if Unity's test suite passes on a clean tree. A passing suite with a dirty repository
> counts as a failure. That rule exists because agents will otherwise 'fix' a test by
> editing the thing it was measuring."

---

## BEAT 6 — The cascade

As 1101 completes, 1107 unblocks; then 1108; then 1110.

> "There's the cascade. Nobody scheduled that order — it falls out of the dependency
> edges in the contracts. The graph is the scheduler."

---

## BEAT 7 — Closing

> "What you're watching isn't one agent in a loop. It's a task graph with ownership
> rules, two-model review on anything that changes the graph's shape, isolated
> checkouts per task, and a test gate that can't be talked around. The human approves
> the things that matter — design decisions, graph changes, and anything visual."

---

## If something fails on camera — say this, don't cut

> "That's a real failure, and it's worth showing. The pipeline classifies failures:
> controller code, fixture policy, provider output, Unity infrastructure, or the task
> implementation itself. A blocked task stops and reports; it doesn't silently retry
> or fake a pass."

Known possibilities:
- **Unity licensing 404** — infrastructure, seen intermittently, not a pipeline defect
- **A task blocking rather than completing** — the correct outcome when a contract
  can't be satisfied honestly

---

## Numbers you can quote

- 9 tasks in scope, 93 hidden — the rest of the real project graph
- 2 real tasks, 7 synthetic
- Decomposition: 2 provider calls, 1 bounded correction round allowed
- Prior full runs: ~23 minutes for 12 tasks; one earlier run took ~45 minutes wall clock
