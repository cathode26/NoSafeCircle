# What Was Reused, and What Was Retired

The private Orchestrator Gauntlet V2 is an accepted, frozen proof of the
decentralized Stage-1 through Stage-4 safety primitives. This document records
what carried forward into the Software Architect Acceptance Gauntlet and what
deliberately did not.

It is operating guidance for this fixture. It is not game-design canon and it
does not change anything about the retired Gauntlet, which must not be replayed
or mutated.

---

## Reused concepts

### Deterministic manifest as test data only

The old `gauntlet_manifest.json` was expectation data that was always
re-derived and cross-checked against the real engine, never treated as a second
source of truth. `scenarios.json` keeps that rule and strengthens it: every
authority-bearing object declares an exact allowed key set, and every readiness
gate, capability, outcome, transition kind, reservation kind, conflict kind,
advisory defect, disjointness verdict and live-evidence check name is validated
against a closed vocabulary.

The strengthening that mattered most came out of the audit: an unknown field is
now an error rather than something silently ignored. A silently ignored field is
a scenario that looks stricter than it is, which is the opposite of what a
gauntlet is for.

### Fixture regeneration checks

`generate_fixture.py --check` proved the old fixture was byte-for-byte
reproducible. The equivalent here is
`test_fixture_generation_is_deterministic_across_two_runs`, which builds the
entire Git fixture twice and requires identical HEAD, tree, branch SHA, branch
diff, tracked list, porcelain status, and working-tree observation.

Reproducibility moved up a level: the old check compared generated file bytes,
this one compares generated **commit identities**, because branch and diff
behavior is what the architect actually reasons about.

The audit correction added the other half.
`test_inherited_git_configuration_cannot_change_a_fixture` sets a hostile
environment, including the `GIT_CONFIG_COUNT` / `GIT_CONFIG_KEY_n` /
`GIT_CONFIG_VALUE_n` command-scope form, and requires the same signature. It
also narrowed the claim: determinism is asserted for one host and one Git
version, and nothing broader, because nothing broader was measured.

### Exact repository and source identity

The old harness recorded exact repository, branch, and commit identity, and
refused to let a path name stand in for authority. `scenarios.json` carries a
`source_identity` block naming the acceptance branch and base commit, the
architect reference branch, and — explicitly — that the architect
implementation is uncommitted and that no scenario has been proven against it.

The live-evidence envelope now enforces the same discipline at run time. Its
`run_metadata` record must carry the repository, source HEAD and tree, scheduler
ID, run ID, and the SHA-256 of the manifest the expectations came from. A
mismatch is refused rather than reported.

### Durable Issue fixture shapes

The old `NSC-601..604` resume/repair fixtures encoded four durable shapes:
recorded FAIL, interrupted lease/branch, pending human decision, and repair
beating fresh work. Those shapes survive as **integration reservations**:
`durable_unmerged_branch`, `human_hold_branch`, `scheduler_active_checkout`,
and `unobservable_surface`, with `workflow_state`/`phase` preserved on each.

Scenario D is the direct descendant of "a pending human decision must not be
replaced by fresh work" — but the reason changed. In the old model the hold
protected an Issue. Here it also reserves a scene.

Scenario I1 is the descendant of "repair beats fresh work", and the audit
sharpened it. Placing the resume task first in a shared queue meant a scheduler
could be right by accident. Resume authority is now a separate durable fact that
does not appear in the fresh Stage-2 ranking at all, and the fresh ranking is
headed by a genuinely launchable candidate with higher advisory confidence.

### Synthetic worker patterns

The old gauntlet ran synthetic work after the production orchestration
boundary, so real selection, claims, Issue lease, checkout and branch behavior
stayed real while the *implementation* was synthetic. The same split applies:
the fixture is synthetic, the adapter drives the real scheduler, and the
`process_factory` seam records argv instead of starting a worker.

### Evidence verification over prose

`verify_gauntlet.py` re-derived every claim from the real engine rather than
trusting a report. `verify_live_evidence.py` keeps that discipline and the audit
extended it: a wait must now carry structured conflicting identities and exact
overlapping tokens. A prose `reason` field may accompany them for a human
reader, but it can never satisfy a structured requirement on its own.

The same rule replaced scenario G2's original design. Disjointness used to rest
on an architect's written justification. It is now recomputed by
`ScenarioWorld.compute_disjointness()` from committed exclusive-resource tokens
and contract identities, and the manifest schema has no justification field at
all.

### Local versus remote verification kept separate

The old verifier printed remote-dependent checks under a distinct
"remote checks (not performed)" heading that never counted toward local
PASS/FAIL. The equivalent is the status vocabulary: `FIXTURE_PASS`,
`HARNESS_PASS`, `PENDING_CAPABILITY` and `UNPROVEN` are all different words
from `PASS`.

The audit added the structural half. The words alone were not enough, because
the caller controlled which word applied. Acceptance now lives in an entry point
that accepts no adapter argument, and a static scan keeps `STATUS_PASS`
assignment confined to it.

The local claim-ref check was also demoted. It inspects one local checkout, so
it is reported as a diagnostic and never gates the exit code; a frozen remote's
authority belongs to the live proof's own repository verification.

### Fail-closed safety refusals with no override

`gauntlet_lib.require_safe_target_repo` refused `cathode26/NoSafeCircle` and
lookalikes with no override flag. `acceptance_lib.require_safe_target_repository`
is the same refusal, and the evidence verifier applies it to the repository
named in a run's metadata.

The filesystem half was rebuilt after the audit found the original
`require_disposable_directory` accepted `/`. There is no longer a predicate that
blesses a caller-supplied deletion target. Fixture roots are created by this
package, marked with an unpredictable token plus device/inode, and deleted only
after that exact identity is re-proven.

### No manual claim cleanup as recovery

The old rule was that leftover claim refs are a finding, not a chore. The live
evidence verifier keeps it: leaked `refs/nsc/claims/**` and a dirty working
tree are reported, and there is no repair path in the harness.

---

## Deliberately retired

### The ten-worker contention wave

`Start-WorkerWave.ps1 -Count 10` launched ten uncoordinated generic workers to
force claim races. That behavior is proven and frozen. The new normal subject
is one scheduler and a bounded worker pool with exact assignments, so a
ten-worker wave would now be testing a retired operating model.

### Independent generic worker self-selection as normal behavior

Workers no longer poll Stage 2 for themselves. They receive an exact
`--task-id`. Scenarios therefore assert *which task the scheduler chose*, not
*who won a race*.

Git CAS claims are kept as defense in depth against a second scheduler, a
manual worker, or a second host — but no scenario here treats racing as the
allocation mechanism.

### Phase A / Phase B naming

The old phases mapped to "resume and human-hold behavior" and "a real
simultaneous fresh-claim race". Neither maps cleanly onto a single-scheduler
model, and reusing the names would imply the old sequencing still applies.
Scenarios are named by letter and behavior instead.

### Fibonacci, dice, and hybrid task fixtures

Arithmetic and a reproducible 2d6 mechanic were the right shape for proving
claims: two workers either both claimed a task or they did not, and a
deterministic result made human review cheap.

They are the wrong shape for conflict reasoning. The question is no longer "did
exactly one worker compute Fibonacci(20)" but "would running these two tasks
concurrently produce a merge conflict in a prefab". That question needs a
repository surface, not an integer. The entire dice/seed/receipt/replay
mechanism is retired along with the tasks it served.

### Fixtures whose only purpose was the decentralized model

`NSC-701..706` negative candidates, the shared-resource contention domains
`NSC-501..510`, and the eighty-five-task graph existed to give ten
self-selecting workers something to contend over. The new gauntlet needs twelve
declared tasks and a handful of files, because the scheduler is the subject and
scale is not the risk.

Exclusive resources survive in a much smaller but sharper role: they are the one
thing that can positively establish disjointness when a surface is unobservable
(scenario G2), and the audit made that the *only* thing that can.

### The automated review simulator

`review_candidates.py` existed because hundreds of synthetic candidates were too
many to review one Issue at a time. A five-to-eight scenario live proof with two
or three workers does not have that problem, and adding an automated reviewer
would reintroduce the exact "proposer approves its own work" risk that the
deferred future scenario M exists to forbid.

---

## Retired during the audit correction

These are not retired old-Gauntlet ideas. They were in the first version of
*this* gauntlet and were removed because they made it easier to fool, not
harder.

### The reference policy adapter

A second, independently written implementation of the documented WAIT rule.
The intent was to check the manifest for internal consistency. The effect was a
second source of scheduling opinion inside a harness whose whole job is to
grade the scheduler against the manifest. It has been removed; declarative
scripted inputs replay the manifest's own expectations instead, and that
agreement is labelled tautological rather than presented as evidence.

### Caller-controlled acceptance provenance

The adapter-kind string, and the verifier logic that read it. Replaced by two
separate entry points, one of which takes no adapter at all.

### Synthesized worker identity

The verifier used to fill in `unnamed-worker-{index}` when a launch carried no
worker ID, and a harness adapter generated worker IDs of its own. Both are gone.
`ScenarioWorld.record_launch` refuses an empty worker ID outright, because a
claim about distinct assignments is worthless if the harness can supply the
identity the scheduler failed to record.

### Actively simulated decomposition scenarios

K, L and M were structurally present and reported `PENDING_CAPABILITY`, which
looked responsible. It was not: their evidence verifier accepted a chain whose
proposal and application carried different plan hashes. Simulating a decomposition
authority chain that does not exist yet adds fake proof, so they are now
documented future specifications in `LIVE_PROOF_CHECKLIST.md` §7 and their event
types are rejected outright.

---

## What changed in kind, not just in scale

| Retired Gauntlet | This gauntlet |
| --- | --- |
| Proved *allocation* safety under contention | Proves *integration* safety before launch |
| Correct outcome: exactly one winner | Correct outcome: a named START, a named WAIT, and the structured reason |
| Randomness was a feature (dice) | Randomness is banned; every fixture SHA is reproducible on one host |
| Scale was the stressor (85 tasks, 10 workers) | Ambiguity is the stressor (unknown surfaces, stale predictions, malformed advisories) |
| Failure mode: duplicate Issue or leaked claim | Failure mode: two branches editing one scene |
| Human review was the bottleneck to automate | Human review is the thing to keep narrow |
| Trusted the harness to report honestly | Assumes the harness will be fooled if it can be, and closes each route structurally |
