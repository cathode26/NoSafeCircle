# Cleanup role revision and independent review — 2026-09-19

Vincent asked for a cautious, faster cleanup plan, an independent Astra project analysis followed by adversarial review, and a Cleanup role that prevents recurrence. This revision addresses those requests through project inspection and documentation/prompt changes. It does not certify any candidate for deletion.

## Independent review and correction

The independent Astra first inspected actual project and runner code and saved its [project analysis](C:/nscrev/reports/nsc-project-analysis-astra-20260919.md), then reviewed the plan in its [adversarial report](C:/nscrev/reports/nsc-team-execution-plan-adversarial-review-astra-20260919.md). Verdict: **FIX FIRST**. The earlier 2–4-hour first-deletion estimate omitted implementation/preparation work and is withdrawn.

The [revised execution plan](C:/nscrev/reports/nsc-team-execution-plan-20260919.md) and [brief](C:/nscrev/reports/astra-team-execution-prompt-20260919.md) now require a small real capture/publication/independent-restore slice, executable helper dispatch cards, complete reverse dependencies and stable fingerprints, maintained writer holds, manifest-last remote recovery, all-log coverage/final drains, and a verified second off-machine copy before unique/dirty/irreplaceable originals retire unless Vincent explicitly decides otherwise.

The current 4–8-hour preparation and 6–12-hour first modest deletion allowances are conditional and unmeasured. They are not a new promise. Many helpers can work concurrently once their actual inputs, backend access and output route are ready; the initial shared heavy-I/O budget is two.

## Cleanup becomes a prevention role

Canonical [Cleanup operating guide](C:/NSC/nsc-cleanup-agent-guide.md), [start/resume prompt](C:/NSC/nsc-cleanup-agent-start.md), and [shared workspace policy](C:/NSC/nsc-workspace-lifecycle-policy.md) establish:

- Producers register persistent workspaces before creation, supply source/parent/dependency and output identities, and own closeout on success, failure, cancellation and handoff.
- Parents account for helper-created clones, nested repositories, running children and every output/log. Registration is self-service; Cleanup does not approve every clone.
- Cleanup maintains one index, bounded reconciliation and an owner exception queue. Artifact acceptance, settled execution and explicit release remain separate facts.
- Retirement requires verified independent recovery and exact current authority. Vincent executes destructive actions.
- Silence, age, patch equivalence, clean status and empty restore logs do not prove disposability. All logs remain evidence.
- The two prefixed protected art refs, art-rejects/NSC-078 and art-rejects/NSC-095, remain explicit holds.
- A registered test sandbox can cover synthetic transient fixtures; retained or unexpected repositories get individual registration. This avoids one receipt per random test fixture without weakening log retention.
- Metrics distinguish new unregistered work, missing closeouts, preservation backlog and verified batches awaiting human execution.

The former Cleanup guide, roster and queue contained unsafe operational rules. Those current rules were replaced. Historical logs were preserved and given a superseding correction. Roster/launch prompts now point to the single canonical Cleanup prompt; CLAUDE, directory, runbook and shared Cleanup memory load the same policy.

Four verified creation sites also gained the contract: merge-verifier, test-runner, ger-drafter and pipeline-reviewer under C:/Users/VincentLiguori/.claude/agents/. Their model/tool metadata was preserved. No additional standing role was created.

## What is ready and what remains

**Ready:** updated operating instructions and startup prompt; manual receipt contract; protected [registry bootstrap](C:/nscrev/reports/cleanup/workspace-registry/README.md); revised execution/preparation plan.

**Still to execute:** existing-session adoption at an authorized checkpoint, seed active/protected registry entries, implement and review launcher registration/closeout hooks, prepare real dispatch cards/tooling and prove the recovery slice. The registry bootstrap contains no fabricated registrations or release certifications. A running session has not necessarily read changed files.

No automatic scheduler, launcher enforcement, archive service, remote repository, backup or deletion runner was installed by this work. No fleet restart, external peer messages, provider CLI launch, Git mutation, move, reset, prune or deletion was performed. Documentation changes cannot guarantee zero future clutter; enforcement, producer compliance and useful human execution windows are still required.

## Preservation and verification

Pre-edit files are byte-preserved under [cleanup-role-before-20260919](C:/nscrev/reports/cleanup-role-before-20260919/manifest.json), including the exact plan/brief audited by Astra. All preserved copies were checked against their recorded SHA-256 values. The original adversarial report refers to these frozen versions; it was not silently changed into approval of revised text.

Verification covered current startup/guide/queue consistency, retirement restrictions, protected refs, lifecycle state vocabulary, Markdown code-fence balance, existing local document links and unchanged helper front matter. No runtime tests were needed for documentation-only changes; no operational safety/restore test is claimed.

Astra's [follow-up assessment](C:/nscrev/reports/nsc-cleanup-review-followup-astra-20260919.md) records its independent assessment of the revised plan and role, separately from the original findings.
