# GER agent runbook

This is the manual, review-only runbook for a held Task Design GER node. It
does not create a graph controller, invoke a provider automatically, reserve a
task, edit a task contract, apply a graph delta, or release a hold. Graph Sol
must exclude the held task manually before every task start; the journal is an
operating record, not CLI enforcement.

Primary Sol and the GER agent own the per-node hold check: before beginning and
after recording every GER result, they must confirm that exact ID is present in
the current unavailable list (currently 32 distinct GER IDs) and record the
run/evidence against it. Graph Sol owns enforcement: before every dispatch it
must read the current journal and exclude every listed ID. There is no supported
graph-state hold toggle and the retired controller is not a substitute for these
manual checks.

## Preconditions and packet preparation

1. Read the current `AGENTS.md`, Graph Sol startup guidance, current graph and
   task state, and `C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\graph-lead-journal.md`.
   Primary Sol/GER must confirm the exact `NSC-###` is listed as unavailable
   before beginning its packet or round, and Graph Sol must make the same
   journal check before every dispatch. Preserve an existing checkout,
   candidate, or evidence; stop an active worker only through its documented
   safe task-specific path and report it to Primary Sol.
2. Work from a clean, committed source. Make a new directory outside the
   repository; never reuse a prior run directory. For example:

   ```powershell
   python Pipeline\TaskDesignGER\task_content_ger.py NSC-080 --output-dir C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\RoomContentGER\20260914-nsc-080
   ```

   Add `--feedback-file <utf8-note>` for visual feedback, or
   `--problem-file <utf8-question> --focus gameplay` for a gameplay question.
   The preparer fails when the selected task, GDD, or art direction is dirty,
   the task is not active, a source reference is invalid, or the output exists.
3. Retain `GER_PACKET.md` and `SOURCE_IDENTITY.json` unchanged. Before every
   human or provider round, verify the task ID, source commit, contract
   revision, hashes, feedback/problem hash, and reference list against
   `SOURCE_IDENTITY.json`, and verify the requested focus from the packet.
   Stop and re-prepare in a fresh directory if any source identity drifts. The
   packet is evidence, never authority to change tasks, the GDD, or the graph.

## Required GER sequence

Use distinct provider identities and preserve one immutable artifact directory
per round. Store the provider name, model, session/conversation identity,
timestamp, packet/source identity, prompt, raw response, structured brief or
findings, and an artifact hash. Do not overwrite an artifact or replace a prior
round. Provider failure, timeout, malformed output, missing identity, or source
drift fails closed and leaves the task held.

1. **Codex Generate.** Create `01-codex-generate/` with a concrete
   review-only brief. Inventory specification gaps, separate current-GDD work
   from design proposals, and give alternatives where the packet asks for them.
   Visual briefs name a focal landmark, supporting clusters, approved-route and
   door relationships, catalog/prefab/builder handoff, and a gameplay-camera
   shot. Gameplay briefs compare projectile survival, melee escape, cover/LOS,
   distance-based target persistence and last-known-position search, controls,
   costs, route tradeoffs, ownership, and tests.
2. **Independent Claude Evaluate.** Create `02-claude-evaluate/`. Claude must
   be a fresh evaluator conversation, distinct from the Codex author, and must
   return evidence-backed findings against the packet, GDD, task contract,
   ownership, dependencies, asset availability, and visible/player-facing
   result. Findings are a union of material issues, never a vote or self-pass.
3. **One bounded Codex Refine.** Create `03-codex-refine/`. The same bounded
   authoring step may resolve every evaluator finding once, with a change log.
   Unresolved design, ownership, asset, test, or scope questions remain open
   for Vincent; do not invent an answer or start another refinement loop.
4. **Fresh Claude re-audit.** Create `04-claude-reaudit/` using a new Claude
   conversation. It must check the refined brief and change log against all
   material prior findings. The latest author never approves its own revision.

Finish with a short `REVIEW_ONLY_BRIEF.md` that links the immutable rounds,
lists unresolved questions, and records exactly one verdict:

- `crew_sized`: the accepted proposed scope is small enough to dispatch after
  the human approval and release process below.
- `needs_execution_decomposition`: approved scope is too broad for one crew;
  retain the same task ID on hold and route it to D1B.2.
- `needs_design`: game-design, GDD, ownership, asset, or test authority is
  missing; retain the hold until Vincent resolves it.

The verdict is review-only. It is neither conformance, task delivery,
readiness, graph approval, nor human approval. Previously delivered work can
enter GER without fabricating conformance; preserve its historical evidence and
state. In particular, NSC-066 remains `not_delivered` until a delivery record
and Vincent's visual pass exist. Its brief must address Vincent's requested
Space-Invaders-lobby-like moving background characters as an original NSC
presentation proposal, with a gameplay-camera visual gate; code presence is
not visual proof.

## Approval, rescope, and release

Vincent reviews the refined review-only brief and explicitly accepts, rejects,
or requests design changes. Record that decision, the exact source/run
identities, evidence paths, verdict, and next action in the unavailable-task
journal. Do not fabricate an acceptance from a provider result.

- For accepted `crew_sized` work, Primary Sol records the acceptance and
  release evidence, removes that exact task ID from the unavailable list, and
  tells Graph Sol it may perform fresh source, dependency, resource, and
  readiness checks before dispatch. Release is explicit; a retained hold is
  not an indefinite state and no tool silently releases it.
- For approved design that changes the task contract, make and review the exact
  contract/GDD change through the normal human-authorized path before execution.
  If the verdict is `needs_execution_decomposition`, retain the parent hold and
  run existing D1B.2 on that same task only after the approved contract design.
  D1B.2 remains review-only until the exact reviewed plan receives its distinct
  human application approval and is applied. Do not hand-number children or
  apply a graph delta from GER.
- After the exact D1B.2 plan is reviewed and applied, record it in the journal,
  clear the obsolete parent hold, and make only executable children eligible for
  Graph Sol's fresh checks. Intermediate children that are still too large stay
  non-dispatchable, are recorded as held, and go through further D1B.2
  decomposition. Recursive decomposition is allowed only through these exact
  reviewed plans.
- For `needs_design`, keep the same task held and send Vincent the missing
  decision. Do not substitute another task, create children, or make the task
  available while it is unresolved.

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
Run review-only GER for <NSC-ID>. First confirm <NSC-ID> remains manually held
in graph-lead-journal.md and prepare a new external source-bound packet. Keep
all four immutable round directories: Codex Generate, independent fresh Claude
Evaluate, one bounded Codex Refine, and fresh Claude re-audit. Record provider
identities, source identity, prompts, raw outputs, hashes, findings, and a
review-only brief. Return exactly crew_sized, needs_execution_decomposition, or
needs_design with evidence. Do not edit tasks/GDD/graph, apply graph deltas,
start a controller, fabricate Vincent approval, or release the hold. If
accepted and crew_sized, Primary Sol must record the release and remove the
exact journal hold before Graph Sol performs fresh readiness checks. If scope
is too large, keep the same task held for D1B.2 after approved contract design.
```
