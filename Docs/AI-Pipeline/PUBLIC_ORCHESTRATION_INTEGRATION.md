# Public orchestration integration

This integration starts at public commit
`73fae3818ded52eec10e12230de7403cafda4081` and selectively ports the reusable
orchestration implementation through rehearsal source boundary
`e942015b2ab8614289ec477487dd183d665744ef`. It does not merge the source
history. Rehearsal task contracts, TaskGraph materializations, game assets,
generated evidence, delivery commits, and merge commits after the original
`bb560d0e56b77156b0d59cd1f60b1ac2fb02a371` boundary remain excluded. The
later reusable selection includes provider profiles, Windows checkout fixes,
decomposition admission/recovery/resume, integration-gate liveness, and the
current read-only GauntletView operator experience.

The explicitly authorized follow-up
`11dcd130665d531d556af48756d4d5291cd3991e` adds bounded workflow-write observation
and post-poll retry handling; its private incident document and historical Issue
fixture are excluded. The equivalent six-event regression uses invented,
canonically hashed events, while a separate public human-PASS regression proves
the new wait classification does not grant automated authority.
The separately authorized visualizer follow-up
`4024531b4f9ea38a5cef6d25d3eae63a0bfa56d9` adds read-only lifecycle, exact GitHub
navigation, local CI snapshots, and persisted usage displays. Its tests use
invented repository identities; its public defaults still read only this
checkout unless the operator explicitly supplies another root.

The public port also keeps shared ExecutionCrew role-capability identities in a
dependency-neutral module. This preserves the exact routing values while
preventing the public CI entrypoint from recursively importing a partially
initialized crew runner through `TaskReviewAgent.__init__`.

The port retains provider routing and session ownership, rigor profiles,
autonomous graph observation, decomposition application and recovery, the
durable integration gate, bounded committed-object reads, trusted Unity runner
provenance and ILPP cleanup, and run evidence reporting. GauntletView retains
the application at that boundary, with public defaults bound to its own checkout.
An external task-state root must be selected explicitly.

Every public task contract and existing evidence file is preserved. The public
project requirements, resource groups and ID map are unchanged. The existing
NSC-020 and NSC-042 validation policies retain their exact task hashes and Unity
filters; an empty decomposition template map supplies the current schema.

No generated rehearsal tasks, game scripts, Unity metadata, test assets,
completion records, live run artifacts, credentials, provider volumes, task
checkouts, or claims are part of this integration. Private workflow identities
are not carried into the added production authority. The synthetic repository
allowlist is empty; explicit and resumed synthetic-enabled runs stop before
creating run state or starting workers. Human PASS and exact-plan decomposition
authorization remain required for public work.

Reusable synthetic protocol tests use fictitious repository identities and
explicit process-scoped test authority. Their contracts, scripts and evidence
exist only in disposable fixture repositories. The production end-to-end test
exercises real controller, reservation, routing, Git and Issue-state code with
fake provider/GitHub/Unity boundaries. These tests establish pipeline regressions,
not Unity gameplay acceptance or a human PASS.

The public deterministic workflows register the public-authority refusal test
and reusable production lifecycle test. The private thousand-run workflow and
its operator runbook are excluded; standalone deterministic scaling fixtures
remain available for offline verification. Full integration verification uses
the Core, Supervisor, Delivery and D1B.2 test inventories plus changed provider,
session, snapshot, decomposition and launcher regression suites. Record each
script's exit status and the exact tested commit and tree; compare any failure
against the exact public base before calling it pre-existing.
