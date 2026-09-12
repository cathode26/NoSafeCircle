# Game task lessons — read before creating a task

Read this before creating or revising a game task, including decomposition children.
Use the relevant lessons to write achievable requirements and choose the right
worker and Unity checks. This is operating experience, not new game-design canon.
Keep it short: add a lesson when evidence changes how we should do the next task.

## Before writing the task

1. **Find a working example.** Check the current project and any relevant project
   under `C:\NSC\SuccessfullTasks`. Record the exact reference commit. Compare
   the complete fix, tests, generated assets and launch path; do not copy only
   the most obvious parameter change. Preserve the reference project.
2. **Separate code from generated Unity content.** Name the scripts, assets,
   prefabs and scenes that must actually change. Identify the Editor menu command
   or batchmode method that creates the generated content, and who will run it.
3. **Match requirements to available tools.** A code-only worker cannot satisfy
   an asset-generation requirement when it cannot run Unity. Assign that step
   to an available Unity-capable tool or Vincent, with an explicit handoff.
   Do not quietly weaken the requirement or ask an agent to rewrite a giant
   serialized texture blob to get around missing tools.
4. **Choose a small regression test first.** Test the behavior that previously
   failed before spending another full crew run. Include the unchanged case
   when refresh, caching or regeneration is involved.
5. **Specify the visible result.** Name the scene, objects and reproduction
   steps Vincent should check. A passing code review is not proof that the
   committed scene or generated asset looks right.
6. **Identify the exact tested version.** Record the starting commit and any
   relevant uncommitted edits. Give Vincent the candidate checkout path and
   candidate commit; preserve his edits and require a new decision after changes.

## NSC-042: repeating wall patterns and stale textures

**Reported 2026-09-10.** Sources: [Claude's investigation](https://github.com/cathode26/NoSafeCircle-Homework-Rehearsal/issues/36#issuecomment-5624042932)
and [Codex's review and correction](https://github.com/cathode26/NoSafeCircle-Homework-Rehearsal/issues/36#issuecomment-5624107966).

Reference: `C:\NSC\SuccessfullTasks\NSC-042`, verified commit
`aee162377a9dbbba4f5862d8629efb69452b2b3b`.
Investigated current commit: `7c0212d7e1c70634bfcb5d631fef3ba3b29ea027`.
These observations describe those versions, not every future checkout.

### A generator fix must also invalidate stale generated content

Claude found that `ArchitecturalTileVisualMatches` in
`Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs` checked
dimensions, rectangle, pixels-per-unit and pivot, but omitted the successful
version's comparison of actual pixels:
`ArraysEqual(sprite.texture.GetPixels32(), pixels)`.

Consequently, changing the wall pattern while retaining the same dimensions
could leave the old `WallTile.asset` untouched even after running the builder.
The current working edit changed `blockWidth` from 48 to 32 but did not restore
that pixel comparison. Porting only the width change was not the complete fix.

**Use this lesson:** test both same-size/different-pixels (must refresh) and
same-size/same-pixels (may reuse). Check the resulting saved asset as well as
the generator. For NSC-042, also test the pattern's repeat period against the
texture width and inspect at least three adjacent wall segments in Unity.

### Code completion and Unity asset generation are separate steps

The investigated AC-005 required the authored `WallTile.asset` and scene to
change, not only generator code and tests. The local worker described by Claude
could not run Unity. Its texture was serialized as 40,960 bytes, represented by
81,920 hexadecimal characters; hand-editing that line was not a sensible
replacement for running the generator.

**Correction to Claude's report:** production already has
`CandidateIntegrator._run_door_prototype_builder` in
`Pipeline/TaskReviewAgent/candidate_integration.py` (definition near line 1154,
callers near 832 and 943 at the investigated version). The missing step was in
the inspected local path; it was incorrect to say no batchmode builder existed
anywhere. Trace the actual selected launch mode before adding another tool.

**Use this lesson:** document the complete sequence: change generator, run the
available Unity builder, check changed assets/scene, then test the exact candidate.
For this task the menu command is **No Safe Circle → Build Door Prototype Scene**.
An asset diff or timestamp indicates regeneration, not visual correctness;
Vincent still needs to inspect the wall pattern.

The controlled manual Build on 2026-09-10 made the bad wall visibly correct and
changed 3,180 of the texture's 10,240 pixels. The resulting texture payload had
zero pixel differences from the preserved successful result. This is strong
evidence that the generator reached the intended output, but the count of changed
pixels alone proves only that materialization happened. Unity also reassigned local
YAML object IDs and serialization order, so whole-file hashes were different even
when the generated pixel payload matched. Validate generated meaning rather than
using raw Unity YAML equality as the oracle.

**Controller defect found 2026-09-10:** the committed NSC-042 validation policy
selected the unrelated `GauntletTests` fixture class. A pipeline could therefore
run Unity successfully without exercising NSC-042's repetition or stale-texture
tests. The policy now selects `DoorPrototypeSceneBuilderTests`. Always verify that
the configured filter names the task's real tests; a green run of the wrong tests
does not validate the task.

### Controlled A/B proved the contract pressure, not a model downgrade

Claude later ran one isolated historical arm and one current arm with identical
starting generator, test, scene and `WallTile.asset` bytes, the same
`claude-sonnet-5` model, and the same Claude Code version. The historical
revision-1 contract reached `REVIEW_READY` using code and tests while leaving
Unity materialization for the builder. The current revision-4 contract contained
AC-005, which explicitly disqualified that stopping point, and failed while
reasoning toward the 81,920-character serialized pixel line. This run exceeded
the provider's 64,000-output-token limit after 36 minutes. An earlier revision-4
run reached the same bad objective by a different route and exhausted 97 turns
while attempting chunked edits.

The larger current turn and timeout budgets did not solve the mismatch. These
runs do not establish that Sonnet was weakened after September 2. They establish
that AC-005 pressured a text-only role toward work that belongs to Unity.

**Use this lesson:** when a writable generator or named builder deterministically
owns a serialized Unity artifact, an LLM must never hand-edit, reconstruct, emit,
or spend context probing the raw payload, even if the artifact path is approved.
The role changes the source-of-truth and names the builder step. The controller
runs deterministic materialization before exact-commit human review. Keep AC-005:
removing it would recreate the stale-asset gap rather than fix the workflow.

Controlled A/B evidence and final report are in
[Issue #36](https://github.com/cathode26/NoSafeCircle-Homework-Rehearsal/issues/36).

### Prompt hard tasks as short evidence loops

A good game-task prompt tells the crew how to obtain feedback, not merely which
files may change. Divide responsibility explicitly:

1. The Linux crew edits source-of-truth code and focused tests.
2. The Windows controller runs the Unity builder and materializes generated
   assets. The containerized crew cannot launch the Windows Unity Editor and must
   never emulate it by hand-editing serialized data.
3. Automated post-Build checks judge measurable behavior. A changed file only
   proves that something changed.
4. Vincent judges appearance after automated checks pass.

Name the builder command and require this bounded cross-environment loop: the crew
implements and returns a candidate; the Windows controller runs Build, inspects
the expected generated paths and runs focused tests; the controller returns a
compact failure report only when those checks expose a source defect. The crew
then revises source code. Run Build a second time to check that an already-correct
target remains equivalent. If Windows Unity is unavailable, the controller stops
at `NEEDS_MATERIALIZATION` with the exact command and expected output paths. It
must not spend more model turns attempting the generated payload. If a visual
requirement has no reliable automated oracle, state that it remains pending
instead of inventing a machine proof.

Use this compact prompt structure for future generated-content tasks:

```text
Visible outcome:
- Describe what Vincent must see and how to reproduce it.

Editable source of truth:
- List generator, gameplay and test files the crew may edit.

Generated outputs:
- List assets/scenes produced by the named Unity builder.
- Do not hand-edit or reconstruct these serialized files.

Evidence loop:
1. Add a focused failing test or measurable invariant.
2. Fix the source-of-truth code.
3. Return the code candidate and request <exact Unity builder>.
4. The Windows controller runs the builder and checks expected output paths.
5. The Windows controller runs <exact focused tests> on the generated result.
6. The controller runs the builder again and checks target equivalence/stability.
7. Revise source only from the controller's concrete failure report.

Failure handling:
- Return exact Unity errors, failed assertions and generated-output observations.
- Revise source only when that evidence identifies a source defect.
- If Unity cannot run, the controller reports NEEDS_MATERIALIZATION and stops.

Human handoff:
- Give the checkout path, exact candidate commit and visual reproduction steps.
- Do not claim visual approval.
```

AC-005 is therefore an end-to-end delivery condition, not an instruction for the
language model to manufacture Unity YAML. It is satisfied after Unity materializes
the result, automated checks pass and Vincent accepts the visible wall. This keeps
the stale-asset protection without recreating the 96-turn payload-editing loop.

### Keep evidence and proposed repairs distinct

Claude's stale-asset conclusion used source and run evidence, not its own direct
pixel comparison. Codex separately reported a byte comparison matching the current
saved texture to the 48-pixel generator and the successful texture to 32.
The proposed small Edit Mode tests are not recorded here as executed tests.
This investigation does not prove that a new candidate has been fixed or approved.

## Add future lessons in this format

- Task/date and a link to the report or exact evidence.
- What failed, what actually caused it, and any remaining uncertainty.
- What the next task author or worker should do differently.
- The smallest useful test and any separate Unity/human check.

For visual bugs, also record a reproducible scene setup, camera/view, relevant
import and material settings, and the expected versus observed appearance.
Include a screenshot or saved reference when available. Check both generated
content and the actual scene objects that use it; a correct texture does not
by itself prove correct tiling, scale, sorting, lighting or camera behavior.

Summarize the lesson here; keep large logs and full agent conversations in their
original evidence locations. Correct disproven conclusions instead of preserving
them as instructions. Do not load every historical report into every new task.
