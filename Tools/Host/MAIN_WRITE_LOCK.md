# Shared main-write lock

`main_write_lock.py` serializes cooperating writers that address the same actual
Git repository. `guarded_merge.py` and GER's `main_write.py` use that helper.
Linked worktrees share its ordinary `refs/locks/main-write` ref. Independent
clones have separate refs: pass the repository being changed, regardless of the
directory containing the tool code.

Each acquisition creates a fresh UUID-bearing JSON blob. Its full object ID is
the release token. The returned handle binds the absolute target, common Git
directory and operation. Roles, process IDs and journal entries are diagnostic;
none grants ownership or same-role reentry. Git failures are errors, not an
invented holder or a free lock.

There is no age-based takeover and `guarded_merge --stale-after` is removed.
Sixty seconds is only an overdue warning. Acquisition timeout bounds how long a
contender waits; it never revokes an owner. The identity API is loaded from the
containing tracked repository or, in a deployed `tools` directory, its workspace's
canonical repository as resolved by `nsc_paths.py`. A missing API or unsupported
host records an explicit unavailable reason; it never authorizes recovery.

## Writer behavior

GER `start(operation, expected_head, repo=..., role=..., journal=...)` acquires,
checks the planned HEAD and records START. It returns the only handle accepted
by `end(handle, new_head, checks)`. Role and journal are bound in that handle.
`transaction(...)` repeats touched-path and index checks, checks the plan's input
bytes, captures restoration bytes under ownership, and retains the lock through
mutation, validation, commit, restoration and outcome recording. Dry runs never
enter the transaction. A stale plan refuses before file mutation.

All five maintained callers participate: `ger/apply_contract.py`,
`ger/contract_commit.py`, `ger/apply_followup_revision.py`, and
`ger-contract-revisions-20260916/new_task_commit.py` and `policy_entry_commit.py`.
The extra committers prefer the bundled sibling GER implementation; standalone
copies may use the maintained deployment. The adjacent historical helper is
never a fallback. A missing shared helper is an import failure, never an unlocked
compatibility path.

The merger requires explicit `--repo` and `--journal`. It checks main and the
current repository state after acquisition, then holds through Git hooks,
validation and reporting. A failed merge or postcommit report preserves actual
state for inspection. It does not promise that a nonzero result means no commit.
An interrupted validator reports `UNCERTAIN`, attempts an uncertainty END record,
and retains ownership even if the journal cannot be written. It never describes
that path as a refusal with an untouched repository.

Ordinary errors attempt journal completion and checked release. Journal or HEAD
observation errors still release, and exit unsuccessfully. Release failure is
visible and an unreleased handle remains retryable. A repeated end/release
cannot clear a later owner or append a second completion record.

`run_process` keeps an interrupted or timed-out mutation child explicit. When
its descendants may still write, the operation retains its full token for
recovery. It does not restore files or release ownership on that path. Normal
subprocess completion establishes that the invoked process finished; hooks and
validators must not deliberately detach additional writers.

## Explicit recovery

The helper's `inspect` subcommand requires `--repo` and prints the current full
token and metadata. Recovery requires that same actual target, the full observed
`--owner-oid`, `--role`, `--reason`, `--termination-established`, and a new
`--report` file. The termination flag is the operator's assertion that the prior
writer and its children/hooks cannot continue; it is not machine proof and must
not be inferred from age or a bare PID.

Recovery first conditionally replaces the inspected token with a fresh recovery
token. A changed token refuses. While still holding ownership, it records actual
HEAD, staged changes, worktree state and in-progress Git markers to the new
report. If inspection or recording fails, it retains and reports its recovery
token. After successful recording it conditionally releases. Clearing the lock
does not reset files, repair a merge, retry a task, or imply the tree is clean.

## Delivery set and later activation

The tracked deployment manifest includes both root files `main_write_lock.py`
and `guarded_merge.py`. A GER-only family deployment excludes root files and
cannot complete this cutover. The Pipeline Maintainer owns activation and
coordinates the GER and Release owners. That owner must deploy those root files,
GER's adapter and three callers together, plus the two extra committers at their
maintained standalone location when those copies are used. The extra family is
still excluded from automatic family deployment; this change does not broaden
that historical archive's deployment scope.

The cutover inventory includes:

- the approved checkout's `Tools/Host` helper, merger, `nsc_paths.py`, `ger`
  adapter and three callers, and `ger-contract-revisions-20260916` extra callers;
- installed root files in `C:\NSC\tools`, plus its `ger` adapter and three callers;
- `C:\nscrev\ger-tools`, currently a junction to `C:\NSC\tools\ger`, including
  entry points invoked through that alias; verify the junction target again at
  cutover rather than treating the alias as an independently deployed copy;
- standalone copies at `C:\nscrev\ger-contract-revisions-20260916\new_task_commit.py`
  and `policy_entry_commit.py`, and
  any launcher-selected alternative roots. Resolve their actual imported GER
  and shared helper, not merely the entry point's location.

At the audit checkpoint the deployed root helper and merger were absent; the
active merger source was `C:\NSC\NSC\NoSafeCircle\Tools\Host\guarded_merge.py`.
These observations describe the pre-cutover machine, not a completed deployment.

Before activation, stop admission of old writer invocations and wait for their
mutation children to finish. Verify resolved paths and hashes against the approved
source, including the helper imported by every caller and alias. Update the
fleet's merger invocation documentation at the same cutover: `--repo` and
`--journal` are required; there is no canonical repository default.

Old GER committers write only the journal and can race either merger despite
the shared ref. Old and new mergers address the same ref; the old pipe-delimited
age parser normally cannot extract an age from a new JSON owner, so it does not
age-break that owner. Its age-based takeover remains unsafe for legacy owners.
Recent open legacy START records without an operation UUID produce a warning in
both new adapters for 30 minutes. This is a transitional diagnostic, not an
admission gate or proof that older writers are absent. Journal read failures are
reported as warnings. Source approval alone is not evidence of deployment, and
tests perform no live activation.

## Focused verification

The existing host-tool runner's `merge` and `ger` families include the helper,
merger, adapter, five entry-point fixtures and both-direction process contention
tests. They use disposable repositories and explicit journals; no real tasks,
providers, live lock or Unity project execution is involved. The deployment
manifest tests verify that declared root files exist in the tracked source.
