# Unity Testing Policy

This document is canonical engineering operating guidance for humans and all model providers. It is not GDD canon and must not be cited as game-design authority.

## Authority and scope

- The selected task contract and current approved GDD define what behavior must be proven.
- This policy defines how tests may safely prove that behavior.
- A model may not invent design while authoring tests. Missing or ambiguous design must be escalated.
- LLM test or validation claims are not execution evidence.

## Test classification

Before editing, every test request must be classified as one or more of:

- pure/component test;
- in-memory scene-builder/generator test;
- committed scene/prefab conformance test;
- Play Mode behavior test;
- serialization/migration test;
- evidence-producing validation run.

The classification must appear in the test-author handoff and determines the required isolation and evidence.

## Non-mutation invariant

- Normal test execution must not modify tracked repository files.
- A passing assertion suite with a dirty Git tree is a failed validation run.
- Ignored logs do not prove the repository stayed clean; tracked and untracked state must be checked explicitly.
- Tests may not save canonical scenes, prefabs, ScriptableObjects, ProjectSettings, task contracts, or GDD files.
- Serialization and migration tests must use temporary assets, copies, temporary repositories, or disposable checkouts.
- A runner must report mutation and preserve it for inspection. It must not automatically restore, reset, clean, delete, or hide changes.

## Scene-builder and prefab-builder rules

- Builder tests use a fresh in-memory test scene or a temporary asset location.
- Normal builder tests never call a production entry point that opens or saves the canonical asset.
- Production menu commands may retain their normal save behavior.
- When safe testing requires a new seam, add only a narrow non-saving seam that preserves production behavior.
- A test-author role must request production testability changes rather than silently making them.

## Unity asset identity

- Move scenes, prefabs, and other Unity assets together with their `.meta` files.
- Never delete or regenerate a tracked `.meta` file as a relocation mechanism.
- Duplicate authoritative scenes with the same filename are prohibited.

## Committed-artifact conformance tests

- Open the exact committed scene or prefab deliberately.
- When scenes are loaded additively, scope object lookup to that exact scene.
- Do not use ambiguous global `GameObject.Find` or `Object.Find` calls across scenes.
- Close the artifact without saving.
- Compare bytes or Git blob identity before and after where practical.
- Distinguish “builder produces this” from “committed artifact currently contains this.” These are different claims and require different tests.

## Isolation and repeatability

- Use explicit setup and cleanup.
- Do not create test-order dependencies.
- Do not rely on the current Editor selection or previously loaded scenes.
- Leave no static or global state behind.
- Tests must work alone, as a class, in the broader suite, and on repeated runs.
- Duplicate and idempotence tests must not persist canonical asset changes.

## Contract and gate mapping

Every test must identify whether it proves:

- an acceptance criterion;
- a completion gate;
- a downstream integration obligation; or
- an explicit regression-only invariant.

The mapping must name the applicable stable contract or gate identifier when one exists. A regression-only test must not be presented as proof of an acceptance criterion or completion gate.

## Evidence claims

Agents and humans must report literally:

- proposed command;
- whether it was actually executed;
- Unity executable and version;
- exit code;
- XML result path;
- total, passed, failed, skipped, and result;
- Git HEAD and tree tested;
- working-tree state before and after;
- known limitations;
- required human runtime or visual checks.

Never say “tests passed” solely because test source appears correct. Static review, an agent claim, a Unity exit code, XML assertions, and repository cleanliness are distinct facts and must not be conflated.

## Human runtime validation

Require human Play Mode, visual, input-feel, framing, readability, animation, or interaction checks wherever source-level assertions cannot prove quality. Automated tests may narrow the review surface but do not replace these judgments.

## Required checklists

### Pre-authoring checklist

- Name the selected task contract and approved canon sources.
- Classify the requested test using the classifications above.
- Map each planned test to an acceptance criterion, completion gate, downstream obligation, or regression-only invariant.
- Identify every scene, prefab, asset, setting, and global state the test could touch.
- Choose an in-memory, temporary, copied, or deliberate read-only committed-artifact strategy.
- Escalate missing design or a required production testability seam before editing outside test authority.

### Pre-run checklist

- Record the proposed command and exact test filter.
- Confirm the intended Unity executable and version.
- Confirm the project is in Git and record HEAD and tree.
- Require a completely clean working tree, including untracked files.
- Confirm result XML and logs will be written outside the repository.
- Identify required human runtime or visual follow-up.

### Post-run checklist

- Record whether the command actually executed and its exit code.
- Require and parse the result XML; report total, passed, failed, skipped, and result.
- Recheck HEAD, tree, tracked changes, and untracked files even when Unity fails.
- Treat changed HEAD or any dirty working-tree state as a failed validation run, including when every assertion passed.
- Preserve and report XML and log paths plus known limitations.
- Do not repair or hide mutation automatically; report changed paths for investigation.

### Required test-author handoff format

```text
Task contract / canon:
Test classification:
Contract or gate mapping:
Files changed:
Isolation strategy:
Canonical assets protected:
Proposed command:
Command actually executed: yes/no
Unity executable/version:
Exit code:
XML path and total/passed/failed/skipped/result:
Git HEAD/tree tested:
Working tree before/after:
Known limitations:
Required human runtime/visual checks:
```

### Blocker/escalation format

When safe testing requires an unapproved production change, stop and report:

```text
Blocked test and contract/gate mapping:
Why existing public behavior cannot be tested safely:
Mutation or ambiguity risk:
Smallest proposed non-saving testability seam:
Production files that would change:
Why production behavior would remain unchanged:
Approval required from:
Safe work that can continue without the change:
```

The test-author role must not implement the proposed production change without approval and appropriate write authority.

## Provider-neutral enforcement

Claude, OpenAI/Codex, future providers, and humans follow this same policy. Provider adapters may translate execution mechanics but may not weaken this policy, its non-mutation invariant, its evidence boundary, or its escalation requirements.
