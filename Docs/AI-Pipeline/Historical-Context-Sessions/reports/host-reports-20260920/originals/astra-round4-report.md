# Round-4 repair of the two FIX-FIRST findings — for Codex / Astra

**Exact commit:** `ca56dc7f075f1b2fa064b34751cb9878787bc849`
on `throughput/background-decomposition` in the isolated clone `C:\nscrev\throughput`,
directly on top of `91a0b0dfd9ad605d39e565b014ea95c099e8d42b`.
Not pushed, not merged. No live run, task contract, Unity Asset, Docker container, GitHub
branch or main checkout was touched; no provider was invoked; every Docker interaction in
the tests goes through the fixture Docker CLI.

**Files changed (7):**

| File | What changed |
|---|---|
| `Pipeline/AssistantControl/background_jobs.py` | both findings |
| `Pipeline/AssistantControl/decomposition.py` | finding 1b (`docker compose run --label`) |
| `Pipeline/AssistantControl/test_background_jobs.py` | 3 new regressions, labelled fixture Docker, 3 updated assertions |
| `Pipeline/AssistantControl/test_decomposition.py` | `ProposalContainerNameTests` extended to the labels |
| `Pipeline/AssistantControl/README.md` | background-jobs section |
| `Pipeline/AssistantControl/CURRENT.md` | dated round-4 section at the top of the background-job entries |
| `Docs/AI-Pipeline/ASSISTANT_AUTONOMOUS_GRAPH.md` | numbered item 7 |

---

## Failing-before evidence

Method: `git worktree add --detach /c/nscrev/before-91a0b0d 91a0b0d`, the **final**
`test_background_jobs.py` and `test_decomposition.py` copied in unchanged, only the new
tests run there; worktree removed afterwards.

### Finding 1 — two checkouts derive the same container identity

`test_two_checkouts_of_the_same_task_never_share_a_container_identity`, both subtests
(`checkout='other checkout root'` and `checkout='other Source clone'`):

```
AssertionError: 'c9eaa73e7cf0b6943f10b70e7d8bbcdaddd018cf37cd4b05f4ff558ff9fa598d'
             == 'c9eaa73e7cf0b6943f10b70e7d8bbcdaddd018cf37cd4b05f4ff558ff9fa598d'
```

`test_a_container_without_this_tickets_labels_is_never_removed`:

```
KeyError: 'labels'     # index["provider_container"]["labels"] — the ticket recorded none
```

`ProposalContainerNameTests.test_run_names_the_compose_container_after_the_run_subcommand`:

```
TypeError: run() got an unexpected keyword argument 'container_labels'. Did you mean 'container_name'?
```

Because the new test module cannot express the old behaviour of the *removal* itself, the
behavioural half is an ad-hoc script (`old_behaviour_finding1.py`: two checkout roots of
the same Source, one shared fixture Docker, same task and identity). On `91a0b0d`:

```
checkout A root      : ...\tmpz9_mnber\checkouts
checkout B root      : ...\tmpz9_mnber\checkouts-b
A job id             : c9eaa73e7cf0b6943f10b70e7d8bbcdaddd018cf37cd4b05f4ff558ff9fa598d
B job id             : c9eaa73e7cf0b6943f10b70e7d8bbcdaddd018cf37cd4b05f4ff558ff9fa598d
same job id          : True
A container          : nsc-decompose-c9eaa73e7cf0b6943f10b70e
B container          : nsc-decompose-c9eaa73e7cf0b6943f10b70e
same container name  : True
A ticket labels      : <none recorded>

B container id       : 22bfa0af4a55a70b
stop in checkout A   : verified_absent
A removed            : ['22bfa0af4a55a70b']
removed B's container: True
containers left      : []
B child still running: True
```

A stop in checkout A **removed checkout B's provider container while B's child was still
running**, and reported `verified_absent`. The same script on `ca56dc7`:

```
A job id             : 75425ac745b3e02935a30f445c6fceafa0255d0557baf9dd8ff23cd6a7b542be
B job id             : cbf8e56ff6544afdb2c091aed4b3a98e5aae47ec5ec652eee6269d3a1c932c19
same job id          : False
same container name  : False
A ticket labels      : {'com.nosafecircle.assistant.job': '75425ac7…',
                        'com.nosafecircle.assistant.checkout': 'd9832a2d…'}
A removed            : []
removed B's container: False
containers left      : ['nsc-decompose-cbf8e56ff6544afdb2c091ae']
B child still running: True
```

(The script teaches only the *fixture Docker* the two label names so it can answer an
inspect on the old commit; the production code there is untouched and ignores labels
entirely — which is the point.)

### Finding 2 — a refusal erases in-flight cleanup progress

`test_authentication_refusal_never_erases_cleanup_progress_or_shortens_the_bound`:

```
AssertionError: Lists differ: ['40fbbf509625f5e8664868ccd24d9158f63da0dcdfd0b2d6f02956cf55ce031f'] != []
First list contains 1 additional elements.
First extra element 0:
'40fbbf509625f5e8664868ccd24d9158f63da0dcdfd0b2d6f02956cf55ce031f'
- ['40fbbf…']
+ []
```

On `91a0b0d` the refusal flipped the in-progress record's `status` to `refused`, so the
owner's `_finish_cleanup` bailed out on `status != "in_progress"` and discarded its
result: the container it had just removed was not recorded, `container_sighted` was lost,
and the record kept the older carried-forward `tombstone_until_utc` — a shorter deadline
than the removal had earned.

---

## Exact behaviour now

### 1. The provider container is checkout-exact and bound to its ticket

**Derivation.** `job_id_for(kind, task_id, identity, attempt, *, source, checkout_root)`
now takes the owning Source path and checkout root as **required keyword arguments** and
hashes them with the rest, so there is no way to derive a ticket id without naming the
checkout. `container_name_for(job_id)` is unchanged, so the name inherits the property:
two checkouts, or two clones of the same Source commit, can never derive the same name.
`launch` passes `manager.source` / `manager.root`; the ticket already recorded both, so
`_identity_problems` re-derives the id from this checkout and reports
`job id is not derived from this checkout, Source, task, identity and attempt` on a
mismatch.

**Labels.** `_provider_container` now also fixes
`labels = {com.nosafecircle.assistant.job: <job id>,
com.nosafecircle.assistant.checkout: sha256({source, checkout_root})}`
on the ticket, for the `decompose` kind and for the test-only `fixture` kind with
`simulate_container`. `decomposition.run` gained `container_labels`: it validates key and
value characters, refuses labels without a named container, records them on the
decomposition record as `container_labels`, and inserts
`--label key=value` (sorted) directly after `--name` in the `docker compose run`
command. The child re-proves them from its own ticket (`_ticket_container_labels`) before
Docker starts, and `_ticket_container_name` now calls it too.

**Enforcement.** `_CONTAINER_INSPECT_FORMAT` reads both labels back as `job` and
`checkout`. `reconcile_provider_container` refuses before any Docker call when the
ticket's own recorded labels are not the ones this checkout derives
(`provider container labels differ from its ticket and checkout; nothing removed`), and
inside the watch loop refuses a sighting whose labels are missing or different
(`container '<name>' carries other identity (job label …, checkout label …); not
removed`) — the same shape as the existing compose-project refusal, so it is retained as
a refused cleanup with nothing removed and the ticket stays pending. Each observation now
records the labels it saw. `_identity_problems` reports
`provider container labels are not derived from this checkout and ticket` for a ticket
whose recorded labels are wrong, so every destructive path already gated by
`_authentication_problems` fails closed on it.

Operator sees: two checkouts never collide by construction; a container under the name
that this ticket cannot prove is its own is never removed, the cleanup is `refused` with
the label mismatch in `error`, `cleanup_pending` stays true, and `stop-background-jobs`
exits 1 until a human resolves it.

### 2. A refusal cannot erase progress or shorten a deadline

`_record_refusal` now distinguishes two cases:

- **A generation in progress under a live owner** (`cleanup_owner_alive`): its `status`,
  `generation`, `owner`, `removed`, `observations`, `container_sighted`,
  `tombstone_until_utc` and `final_recheck_at_utc` are left exactly as they are and the
  refusal is recorded beside them as `refusal_error` + `refused_at_utc` +
  `authentication_failed`.
- **Nothing in flight** (or an owner that is gone): `status` becomes `refused` and every
  progress field above is still carried unchanged. `tombstone_until_utc` is passed through
  `_later_utc`, so a refusal can only ever keep or extend the recorded bound.

`_finish_cleanup` still accepts its own generation when a refusal marked it before it
finished — it matches on `generation` plus the absence of `finished_at_utc`, so it also
covers a refusal written by a process that could not see the owner as alive. It records
the removals (merged cumulatively), the sighting, and the renewed bound through
`_later_utc`, then forces the generation to land as `status: refused` with
`authentication_failed: true`, `verified_at_utc: None` and `final_recheck_at_utc: None`
(the generation's own Docker error, if any, is kept as `reconcile_error`). A ticket that
does not authenticate can therefore never read as verified, and no retry can run against
a deadline shorter than the one the removal earned: `_begin_cleanup` carries
`tombstone_until_utc`, `final_recheck_at_utc` and `container_sighted` forward, and
`_record_final_recheck` still refuses a generation whose `container_sighted` is set.

`container_sighted` remains **each generation's own verdict** (not sticky): a later
generation that looks again and sees nothing is what earns the final recheck. Carrying it
forward only keeps an in-flight record honest until its own generation reports. (Making it
sticky wedged the cleanup permanently — caught in self-audit and reverted.)

Operator sees: the refusal on the record (`authentication_failed`, the problem list in
`authentication`, `refusal_error`/`error`), the removals that did happen, a
`retry_after_utc` no earlier than before, `cleanup_pending` true, and no automatic retry
(`cleanup_retry_due` is false while `authentication_failed` is set).

---

## Tests

New regressions (all fail on `91a0b0d`, all pass on `ca56dc7`):

| Finding | Test |
|---|---|
| 1 | `test_two_checkouts_of_the_same_task_never_share_a_container_identity` (other checkout root, other Source clone) |
| 1 | `test_a_container_without_this_tickets_labels_is_never_removed` (unlabelled, another checkout, another job) |
| 2 | `test_authentication_refusal_never_erases_cleanup_progress_or_shortens_the_bound` (live owner, dead-looking owner, nothing in flight) |

They assert, respectively: different job ids, container names, labels and Job Object
names; that a stop in one checkout inspects and removes only its own name (asserted
against `FixtureDocker.calls`), leaves the other checkout's container present, its child
`running`, and writes no stop request for it, and that the other checkout can still
finish its own cleanup; that a wrongly-labelled container is refused with nothing removed
and the ticket stays pending, that a ticket whose own labels are wrong is refused before
Docker is asked at all, and that the correctly labelled container is then removed
normally; and that an in-flight generation's removal, sighting and renewed bound survive a
refusal, that it lands `refused` + `authentication_failed` and never verified, that a
refusal with nothing in flight preserves `generation`, `removed`, `observations`,
`container_sighted`, `tombstone_until_utc`, `final_recheck_at_utc` and
`tombstone_seconds`, and that the final recheck still completes once the bound has passed.

`ProposalContainerNameTests` now asserts the exact
`run --name … --label com.nosafecircle.assistant.checkout=… --label
com.nosafecircle.assistant.job=… --rm -T` argument slice, the recorded
`container_labels`, and that a bad label key and labels without a named container are both
refused.

The real detached Windows test
(`test_real_restart_adopts_a_live_tree_then_quarantines_and_ends_it_with_its_container`)
now creates its fixture-ticket container with the labels this checkout derives and asserts
the ticket recorded exactly them, so the labelled path is exercised end to end through a
real `DetachedHost` with the fixture Docker runner. `FixtureDocker` gained `expect(...)`
(registered by `FixtureHost.spawn` from the request, the way the real child stamps its own
ticket's labels), a `labels=` argument on `create`, and reports both labels on inspect,
returning empty for a label the container does not carry — as `index .Config.Labels` does.

Three existing assertions on the exact `provider_container` dict were extended with the
derived labels (a strengthening, not a relaxation).

Results on `ca56dc7`:

```
python -m unittest Pipeline.AssistantControl.test_background_jobs
Ran 53 tests in 92.670s
OK

python -m unittest Pipeline.AssistantControl.test_graph_controller
Ran 33 tests in 41.564s
OK

python -m unittest Pipeline.AssistantControl.test_decomposition Pipeline.AssistantControl.test_cli_worker Pipeline.AssistantControl.test_worker_control
Ran 17 tests in 12.624s
OK
```

`git diff --check`: clean, exit 0 — the only output is the expected
`LF will be replaced by CRLF` notice for the two LF files.

One earlier full run of `test_background_jobs` (before the last two code refinements)
reported an error in `test_real_detached_child_tree_is_terminated_on_forced_stop`, a real
detached-Windows-child test that waits up to 30 s for its marker file. It passed
standalone immediately afterwards and on all three subsequent full runs. That test uses
`kind="fixture"` **without** `simulate_container`, so it creates no provider container and
touches none of the changed code; the machine was running other suites concurrently. I am
recording it rather than hiding it, but I could not reproduce it.

---

## Residual risks and operator burden, stated plainly

- **Migration burden, and the one I would most like you to rule on.** Changing the job-id
  derivation makes every ticket written before this commit fail authentication: the job id
  no longer re-derives and the ticket carries no labels. Such a ticket records
  `authentication_failed`, is never retried automatically, refuses startup — and
  `clear-background-job` refuses it too, because `clear` authenticates first. There is
  deliberately no bypass. So before this branch is merged onto a checkout that has any
  retained background-job index, an operator must archive the
  `.assistant-control/NSC-*.background-job.json` files by hand (and remove any leftover
  `nsc-decompose-*` container themselves). No live run currently uses this branch, so
  nothing is stranded today, but a merge note is needed.
- `_docker_stop` (the child's cooperative interrupt) still stops by container name without
  checking labels. The name is now checkout-exact, so it can no longer reach another
  checkout's container, but it is a `docker stop` on a name rather than a label-verified
  removal.
- The compose-project and service checks run before the label check, so a container from
  another compose project is still reported as a project mismatch rather than a label one.
  That is the same refusal shape and the same outcome (nothing removed).
- The checkout label is a hash of the Source path **and** the checkout root as strings.
  Two checkouts reached through different but equivalent paths (a substituted drive, a
  symlink, a UNC alias) would derive different identities and would not recognise each
  other's containers — fail-closed, but it means a checkout must be addressed
  consistently. `Checkouts` resolves both paths, which covers the common cases.
- A refusal landing on a generation whose owner then dies before `_finish_cleanup` leaves
  the record `refused` with that generation number and no `finished_at_utc`; the removals
  it had already made are in `removed` only if it reached `_finish_cleanup` or
  `_finish_interrupted`. A kill -9 between the `rm -f` and either is still a lost removal
  — bounded by the tombstone, which is why the bound survives.
- The `authentication_failed` cleanup still needs an operator, unchanged from round 3.
- The real `docker` CLI path remains exercised read-only; the fixture Docker drives every
  mutation test, including the new label checks.

---

Requesting Astra's re-review of **`ca56dc7f075f1b2fa064b34751cb9878787bc849`** before merge.
