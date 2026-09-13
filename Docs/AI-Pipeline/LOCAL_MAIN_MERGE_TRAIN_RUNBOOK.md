# Local Main Merge Train Runbook

This document defines the host-operated process for collecting completed local
branches into the local `main` branch while other workers continue on isolated
branches. It is operating guidance, not GDD canon and not evidence that any task
is complete.

This merge train is for an explicitly authorized local preview of combined
work. It does not replace the task delivery lifecycle, the durable integration
gate, exact candidate approval, required CI, or remote publication authority.
It never grants permission to push.

## Required result

At the end of a successful train:

- every included branch is identified by an exact commit;
- the combined tree is committed and validated in a disposable integration
  checkout;
- local `main` advances only by fast-forward to that tested commit;
- the canonical checkout remains clean;
- the local graph viewer is restarted from the new `main` and shows the full
  current graph;
- active, blocked, review-gated, and excluded work remains visible and is not
  misreported as complete.

A failed train stays isolated. Workers on unrelated branches continue.

## Roles and write ownership

Use one checkout for each role:

| Role | Responsibility |
| --- | --- |
| Canonical checkout | Holds local `main`; receives only the final verified fast-forward. |
| Integration checkout | Disposable branch where exact candidate commits are merged and tested. |
| Worker checkout | Owns one task or disjoint change set; never writes another worker's files. |
| Merge-train owner | Inventories candidates, resolves conflicts, runs gates, records evidence, and updates local `main`. |
| Viewer process | Reads the canonical checkout after the fast-forward; never supplies merge authority. |

Only one merge-train owner may write local `main` during the final integration
window. This freezes writes to local `main`, not implementation work. Workers
continue producing commits on isolated branches for the next train.

Every path family has one producer. For Unity-generated assets, the producer
also owns the corresponding `.meta` files and importer settings. Two branches
must not independently generate identity for the same asset family.

## 1. Snapshot the train

Before merging:

1. Verify the canonical checkout is on `main` and completely clean, including
   untracked files.
2. Record the exact local `main` commit and tree.
3. Inventory every possible input branch and exact head commit.
4. Classify each input as complete and eligible, active, blocked, awaiting
   human review, or superseded.
5. Include only commits whose implementation and review boundary is understood.
   Carry all other work visibly into the next train.
6. Record the expected changed paths and the producer responsible for each path
   family.

An Issue label, green viewer color, branch name, or agent statement is not proof
that a commit is eligible. Inspect the exact commit and its durable records.

## 2. Assemble only in the integration checkout

Create or reset a disposable integration branch at the recorded local `main`
commit. Confirm its worktree is clean before the first merge.

Merge exact commits one at a time in dependency order. After each merge:

1. record the new integration commit or unresolved merge state;
2. inspect the complete changed-path set;
3. run the smallest deterministic checks that can expose an integration defect;
4. stop adding candidates when the current failure is not understood.

Do not merge directly in the canonical checkout while discovering conflicts.
Do not rebase or rewrite worker branches as part of this process. Preserve
coherent worker commits and add explicit merge or integration-fix commits so
reviewers can distinguish authored work from reconciliation work.

## 3. Resolve conflicts from evidence

First inventory every unresolved path and prove whether the set is homogeneous.
Do not apply one automatic resolution strategy to a mixed conflict set.

Resolve ordinary source conflicts by preserving the required behavior from both
parents when the features are compatible. Add an integration regression when a
conflict exposes an interaction that neither branch tested alone.

For Unity assets and `.meta` files:

1. Keep an asset and its `.meta` identity together.
2. Never regenerate a tracked `.meta` file to make a conflict disappear.
3. Find which GUID is referenced by scenes, prefabs, controllers, clips, and
   other serialized assets.
4. Retain the referenced GUID and its complete importer configuration.
5. Verify every retained serialized GUID resolves to exactly one tracked
   `.meta` file.
6. Verify sprite pivots, pixels per unit, filtering, compression, mipmaps, and
   other importer settings required by the game.
7. Confirm no incoming branch contains a unique asset path that was discarded.

`ours` or `theirs` is acceptable only after these checks prove that one complete
side is authoritative for the entire homogeneous conflict set.

## 4. Apply the validation ladder

Run validation from cheapest to most expensive. A later green result does not
erase an earlier unexplained failure.

1. Confirm there are no unresolved index entries.
2. Run the whitespace and patch check.
3. Validate TaskGraph contracts, parent edges, dependencies, execution groups,
   and requirement indexes when graph files changed.
4. Run focused unit and integration tests for every changed pipeline module and
   every conflict-resolution seam.
5. Run broader Python or host-side suites when shared pipeline behavior changed.
6. From a clean committed integration checkout, run the required Unity Edit Mode
   tests with results outside the repository.
7. From the same exact commit, run the required Unity Play Mode tests with
   results outside the repository.
8. Parse the result XML and record total, passed, failed, skipped, result, Unity
   executable/version, commit, and tree.
9. Recheck the complete Git worktree after each authoritative Unity run. Any
   mutation makes that validation fail even when assertions passed.
10. Perform the named human Play Mode or visual checks when automated assertions
    cannot prove appearance, input feel, framing, readability, or animation.

Use the repository's clean Unity runner and follow
`Docs/Engineering/UNITY_TESTING_POLICY.md`. Workspace hygiene may diagnose or
clean interactive editor churn before validation; it must not hide mutation from
an evidence-producing run.

## 5. Handle a moving local main

Immediately before advancing local `main`, compare the canonical head with the
recorded snapshot.

If it is unchanged, continue. If it moved:

1. inspect the new commits and changed paths;
2. merge the new exact head into the disposable integration branch;
3. rerun every gate affected by that delta;
4. repeat the head comparison.

If local `main` keeps moving, establish a brief named integration window in
which no other process writes `main`. Do not stop workers; direct their completed
commits to the next train.

## 6. Advance local main

The canonical checkout must still be clean, on `main`, and at the exact verified
ancestor. Advance it by fast-forward only to the tested integration commit.

Afterward, verify:

- canonical `HEAD` equals the tested integration commit;
- the expected first-parent and merged ancestry is present;
- the canonical tree equals the tested integration tree;
- the canonical worktree is completely clean.

Do not force-update, reset, squash, push, or publish as part of the local merge
train. Remote delivery remains a separate authorized lifecycle.

## 7. Restart and verify the graph viewer

Stop only the viewer process proven to be serving the canonical repository and
expected port. Start a new viewer process with the canonical checkout as both
its working directory and source root. Keep timestamped stdout and stderr logs.

Prewarm the state endpoint, then verify:

- the viewer reports the new canonical commit and source path;
- the API returns the expected total task count;
- the full graph is visible rather than only the current execution slice;
- active, blocked, review-gated, completed, and outside-current-run tasks use
  distinct labels;
- a timeout or broken task record appears as an explicit diagnostic instead of
  silently removing nodes.

The viewer is an observation surface. It cannot mark work complete, approve a
candidate, or authorize a merge.

## 8. Record the train

The closeout must state:

- original and final local `main` commits;
- every included branch and exact commit;
- every deferred branch and why it was deferred;
- conflict paths, ownership decision, and supporting evidence;
- integration-fix commits;
- each test command actually executed and its result;
- Unity XML/log paths and worktree cleanliness;
- viewer source, commit, task count, and startup log;
- known limitations and remaining human checks;
- whether any remote mutation occurred.

## Failure and recovery

When a merge, test, Unity run, or viewer verification fails:

1. leave local `main` unchanged;
2. preserve the integration branch, failing commit, logs, and conflict state;
3. classify the failure as candidate defect, interaction defect, test-fixture
   defect, environment failure, or uncertain state;
4. assign the repair in a disjoint checkout when other work can continue;
5. rerun the affected gate after the repair;
6. escalate repeated runner failures under the repository's two-strike rule.

Never clean, reset, or discard an uncertain integration state merely to make the
train appear green. The graph keeps moving because failed integration is
isolated and its blocker is visible.

## Merge-train checklist

- [ ] Canonical `main` is clean and its exact commit/tree are recorded.
- [ ] Candidate branches, exact commits, states, and path owners are inventoried.
- [ ] One owner controls the local-main write window.
- [ ] Unity asset and `.meta` generation has one producer per asset family.
- [ ] Exact commits are merged one at a time in a disposable checkout.
- [ ] All conflicts are inventoried and resolved from code or serialized-reference evidence.
- [ ] There are no unresolved index entries and the patch check passes.
- [ ] TaskGraph and focused pipeline tests pass where applicable.
- [ ] Required Unity Edit Mode and Play Mode runs pass on the clean exact commit.
- [ ] Human visual/runtime checks are recorded where required.
- [ ] A moved local `main` is reintegrated and affected gates are rerun.
- [ ] Canonical `main` advances by fast-forward only.
- [ ] The canonical checkout is clean after the fast-forward.
- [ ] The graph viewer is restarted from canonical `main` and shows the full graph.
- [ ] The closeout records included, deferred, failed, and remote-mutation state.
