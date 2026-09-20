# GER agent runbook

This runbook takes a held Task Design GER node through the full cycle:
independent mixed-provider design review, an improved task contract committed to
canonical `main`, any required D1B.2 decomposition applied through the supported
graph path, and release of executable work. The GER owner runs the rounds and
makes those contract and graph changes; Primary Sol manages graph workers. GER
round artifacts stay outside the repository. GER never starts a graph controller
or graph workers and never pushes. Graph Sol must exclude every held task
manually before each task start; the journal is an operating record, not CLI
enforcement.

The live graph viewer on port 8828 reads display markers from
`C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\held-task-ids.json`.
The GER owner marks a held node active when GER work starts. This displays the
node in the brown **Task Retired color** while keeping the real task contract and
delivery state unchanged. The marker is a viewer annotation, not retirement.
After the improved contract and any required decomposition are committed and
applied, the GER owner releases the hold and the executable task appears purple
**Task Unstarted**. A decomposed parent remains **Decomposed Parent**; its
executable children appear purple.

**If the refined task is too large for one worker, the GER owner must route it
through task decomposition before releasing executable work.** Keep the task
held while the reviewed decomposition plan is prepared and applied.

## Viewer marker procedure

Run these commands from the canonical source checkout that serves the live viewer,
`C:\NSC\NSC\NoSafeCircle`, against the **live** checkout root below. Do not
write a separate viewer-only control root; it will show zero live workers.
The journal hold, not the JSON marker, controls dispatch exclusion. From Git Bash,
write the checkout root with forward slashes (`C:/NSC/NoSafeCircle-AssistantCheckouts`);
unquoted backslashes are consumed by the shell.

At the start of GER work on a node, after confirming the ID is held in both
the journal and JSON file:

```powershell
python -m Pipeline.TaskDesignGER.ger_viewer_marker start NSC-080 --checkout-root C:\NSC\NoSafeCircle-AssistantCheckouts
```

If work is blocked or waits for a game-design decision, clear only the temporary
brown activity marker. Keep the task held and gray **Outside Current Run**:

```powershell
python -m Pipeline.TaskDesignGER.ger_viewer_marker pause NSC-080 --checkout-root C:\NSC\NoSafeCircle-AssistantCheckouts
```

After the task's improved contract is committed and any required decomposition
is applied, the GER owner removes that exact ID from the journal hold and
releases its viewer hold. For a crew-sized task:

```powershell
python -m Pipeline.TaskDesignGER.ger_viewer_marker finish NSC-080 --checkout-root C:\NSC\NoSafeCircle-AssistantCheckouts
```

For an applied decomposition, name only executable, unheld children; a child
that still needs decomposition stays held until its own reviewed split applies:

```powershell
python -m Pipeline.TaskDesignGER.ger_viewer_marker finish NSC-080 --checkout-root C:\NSC\NoSafeCircle-AssistantCheckouts --ready-child NSC-101 --ready-child NSC-102
```

The command edits only the live viewer JSON atomically. `start` requires an
existing hold, `pause` leaves the hold intact, and `finish` removes that hold.
The finished marker changes presentation to purple; the detail panel still
shows the authoritative task state. Never use `finish` for `needs_design`, an
uncommitted contract, or a decomposition that has not been applied. Reload the
viewer after each change (a page loaded earlier keeps its old colors) and confirm
the specific node's color and detail.

The GER owner owns the per-node hold check: before beginning and after recording
every GER result, confirm that exact ID is present in the current unavailable
list and record the run/evidence against it. Graph Sol owns enforcement: before
every dispatch it must read the current journal and exclude every listed ID.
There is no supported graph-state hold toggle and the retired controller is not
a substitute for these manual checks.

## Preconditions and packet preparation

1. Read the current `AGENTS.md`, Graph Sol startup guidance, current graph and
   task state, and `C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\graph-lead-journal.md`.
   Confirm the exact `NSC-###` is listed as unavailable before beginning its
   packet or round; Graph Sol makes the same journal check before every
   dispatch. Preserve an existing checkout, candidate, or evidence; stop an
   active worker only through its documented safe task-specific path and report
   it to Primary Sol.
2. Recheck that canonical `main` is clean and note its HEAD before every packet.
   Make a new directory outside the repository; never reuse a prior run
   directory. For example:

   ```powershell
   python Pipeline\TaskDesignGER\task_content_ger.py NSC-080 --output-dir C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\RoomContentGER\20260914-nsc-080
   ```

   Add `--feedback-file <utf8-note>` for visual feedback, or
   `--problem-file <utf8-question> --focus gameplay` for a gameplay question.
   The preparer fails when the selected task, GDD, or art direction is dirty,
   the task is not active, a source reference is invalid, or the output exists.
3. Retain `GER_PACKET.md` and `SOURCE_IDENTITY.json` unchanged. Before every
   provider round, verify the task ID, source commit, contract revision, hashes,
   feedback/problem hash, and reference list against `SOURCE_IDENTITY.json`,
   and verify the requested focus from the packet. Providers read a frozen copy
   of the packet's source commit outside the repository (for example a
   `git -c core.autocrlf=false archive` snapshot), so later unrelated commits on
   `main` do not change a round. Stop and re-prepare in a fresh directory if the
   selected task, GDD, art direction, or references change on `main`. The packet
   is evidence; the contract edit below is the only task change GER makes.

## Required GER sequence

Use distinct provider identities and preserve one immutable artifact directory
per round. Store the provider name, model, session/conversation identity,
timestamp, packet/source identity, prompt, raw response, structured brief or
findings, and an artifact hash. Do not overwrite an artifact or replace a prior
round. Provider failure, timeout, malformed output, missing identity, or source
drift fails closed and leaves the task held.

Every round examines the GDD, references, theme, content, visual composition,
gameplay mechanics, missing specification, file ownership, dependencies, and
meaningful tests. A proposed test must exercise the production path it claims to
prove.

1. **Codex Generate.** Create `01-codex-generate/` with a concrete brief and a
   complete proposed task contract. Inventory specification gaps, separate
   current-GDD work from design proposals, and give alternatives where the
   packet asks for them. Visual briefs name a focal landmark, supporting
   clusters, approved-route and door relationships, catalog/prefab/builder
   handoff, and a gameplay-camera shot. Gameplay briefs compare projectile
   survival, melee escape, cover/LOS, distance-based target persistence and
   last-known-position search, controls, costs, route tradeoffs, ownership, and
   tests.
2. **Independent Claude Evaluate.** Create `02-claude-evaluate/`. Claude must
   be a fresh evaluator conversation, distinct from the Codex author, and must
   return evidence-backed findings against the packet, GDD, task contract,
   ownership, dependencies, asset availability, tests, and visible/player-facing
   result. Findings are a union of material issues, never a vote or self-pass.
3. **One bounded Codex Refine.** Create `03-codex-refine/`. The same bounded
   authoring step resolves every evaluator finding once, with a resolution log,
   and returns the complete final proposed contract. Unresolved design,
   ownership, asset, test, or scope questions stay open for Vincent; do not
   invent an answer or start another refinement loop.
4. **Fresh Claude re-audit.** Create `04-claude-reaudit/` using a new Claude
   conversation. It checks the refined brief, resolution log, and final contract
   against all material prior findings and recommends `commit_contract`,
   `commit_contract_then_decompose`, `needs_design`, or `blocked_not_design`.
   The latest author never approves its own revision.

## Result and verdict

Finish with a short `GER_RESULT.md` that links the immutable rounds, the
contract commit, any decomposition plan and application, and unresolved
questions, and records exactly one verdict:

- `crew_sized`: after the committed contract, one worker can complete the task.
- `needs_execution_decomposition`: the committed contract is too broad for one
  crew; keep the same task ID on hold and route it to D1B.2.
- `needs_design`: game-design, GDD, ownership, asset, or test authority is
  missing; keep the hold and ask Vincent for the exact decision.

Provider results are evidence, not conformance, task delivery, readiness, or
human approval. Previously delivered work can enter GER without fabricating
conformance; preserve its historical evidence and state. In particular, NSC-066
remains `not_delivered` until a delivery record and Vincent's visual pass exist.
Its GER must address Vincent's requested Space-Invaders-lobby-like moving
background characters as an original NSC presentation proposal, with a
gameplay-camera visual gate; code presence is not visual proof.

## Contract edit, decomposition, and release

- **Contract edit.** When the fresh re-audit recommends `commit_contract` or
  `commit_contract_then_decompose`, the GER owner applies the audited contract
  JSON, plus only the re-auditor's quoted minor edits, to `Tasks/<NSC-ID>.yaml`
  on current `main` after confirming that file is unchanged since the packet.
  Increment `contract_revision`, record the GER run in `provenance`, run
  `python Pipeline/TaskGraph/taskcontrol.py validate`, stage exactly the changed
  task paths, and commit with a non-attributable `.invalid` identity. A GDD or
  approved-design change needs Vincent's explicit decision first.
- **Coordinate with Primary Sol.** Commit on top of current `main`; never reset,
  rebase, or rewrite history. Running graph workers keep their pinned source.
  Record every GER commit in the journal so Graph Sol's fresh source, dependency,
  resource, and readiness checks see it. Do not push without separate
  authorization.
- **Crew-sized release.** After the contract commit, remove that exact task ID
  from the journal hold, run `finish`, reload the viewer, and tell Graph Sol it
  may perform fresh checks before dispatch. Release is explicit; no tool silently
  releases a hold.
- **Decomposition.** Keep the parent held and run D1B.2 on the committed
  contract, following `Docs/AI-Pipeline/DECOMPOSITION_CHECKOUT_ISOLATION.md` and
  `Pipeline/TaskDecomposition/README.md`. Apply the exact reviewed plan through
  the supported graph-application path, and ask Vincent for exact-plan
  authorization where that tool requires it. Never hand-number children or edit
  a graph delta. Record the applied plan in the journal, then release only
  executable children with `finish --ready-child`. Children that are still too
  large stay held and go through their own GER contract check and D1B.2 split.
- **Needs design.** Run `pause`, send Vincent the exact decision, and continue
  with the next held node. Resume the same node with a fresh packet after his
  answer. Do not substitute another task, create children, or release it while
  it is unresolved.
- Never claim an approval, test result, or validation that did not happen.

## Verification before handoff

Check the production preparation path, not only a synthetic fixture: run the
preparer for the selected real held task into a new external directory and
verify the emitted packet and source identity against the committed source.
For a runbook change, also check Markdown links, headings, all four required
round names, all three verdict values, and the explicit release branches above.
Do not call a provider, Docker, a graph controller, or graph-application tool
as part of this documentation check.

## Paste-ready agent prompt

```text
Run full-cycle GER for <NSC-ID>. First confirm <NSC-ID> remains held in
graph-lead-journal.md, recheck the clean main HEAD, and prepare a new external
source-bound packet. Start the live viewer marker (brown Task Retired). Keep all
four immutable round directories: Codex Generate, independent fresh Claude
Evaluate, one bounded Codex Refine, and fresh Claude re-audit, recording provider
identities, source identity, prompts, raw outputs, hashes, and findings. Turn the
audited result into concrete task-contract edits on main, validate them with
taskcontrol.py, and commit them with a .invalid identity; never push. If the task
is too large for one worker, run D1B.2 and apply the reviewed plan through the
supported graph path, recursively decomposing children that are still too large.
Keep the task held until its contract and any decomposition are finished, then
remove the journal hold and run finish so executable work shows purple Task
Unstarted; a decomposed parent remains Decomposed Parent. If blocked or waiting
for a game-design decision, run pause, ask Vincent the exact decision, and
continue with the next held node. Record exactly crew_sized,
needs_execution_decomposition, or needs_design in GER_RESULT.md. Do not claim
approval or test results that did not happen.
```
