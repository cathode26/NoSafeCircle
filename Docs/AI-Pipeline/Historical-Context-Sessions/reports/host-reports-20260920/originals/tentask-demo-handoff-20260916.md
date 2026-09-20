# TenTask demo run — handoff (2026-09-16)

Written at the end of a session whose context was full. Everything below is verified,
not remembered.

## Repo state I left behind

`C:\NSC\TenTaskFinalIntegration-20260905`

- Created branch **`demo/run-20260916`** at `4ecf3fa`, currently checked out.
  This is the only mutation. Working tree clean, `main` untouched, nothing pushed.
- To undo: `git checkout main && git branch -d demo/run-20260916`
- Fresh empty checkout root exists at `C:/NSC/TenTaskFinalIntegration-20260905-DemoRun`.
- `validate` PASSes: 76 tasks, 17 active, 59 cancelled.
- `graph-plan` returns `actionable` with `prepare NSC-042` and `prepare NSC-1001`.
- NSC-042 is rev 4 with AC-005, `not_delivered`, no dependencies.

## This build is OLDER than canonical — two real differences

1. **`graph-preflight` does not exist.** Not a bug, not a missing flag — the subcommand
   isn't in the parser. Launch `run-graph` directly. This *removes* the preflight-binding
   mismatch problem entirely; don't go looking for it.

2. **`run-graph` has no `--background-jobs`.** Passing it is an argparse error.
   The flags this build actually accepts:
   `--task  --worker-config  --human-review-task  --auto-approve-gauntlet`
   `--authorize-provider-spend  --capacity  --target-branch  --scope-dir  --providers`
   `--compose-project  --max-actions  --once  --delegate-safe`

   `HUMAN_ONLY_TASKS = frozenset({"NSC-042"})` is present here too
   (`Pipeline/AssistantControl/automation_policy.py:16`), so NSC-042 must be passed as
   `--human-review-task`.

## The "why does it turn blue a second time" question

**The state you want already exists.** `Pipeline/TaskReviewAgent/GauntletView/index.html:310`:

    integration_queued: { color: '#f8fafc', label: 'Candidate Ready — Waiting for Merge Gate', group: 'in flight',

So this is **not** a missing state and **not** a legend problem. Something is returning the
task to the active/blue state instead of assigning `integration_queued`. Start in the
controller's state assignment, not in the viewer.

Unread lead: `index.html:858` skips `integration_queued` entirely when
`snap.run.mode === 'local_rehearsal'` —

    if (snap.run.mode === 'local_rehearsal' && ['complete', 'checks_pending', 'integration_queued'].includes(state)) continue;

If this run reports mode `local_rehearsal`, that line alone could explain why the state is
never displayed. **Verify the run's actual mode before touching any controller code** — this
is a plausible cause, not a confirmed one.

## Separate, still-unapplied viewer fix

Run-detail rows render the literal string `Unavailable` when their value is null
(`local_runtime_patch_sha256`, `github_url`). Vincent wants those rows hidden instead.

Anchors, confirmed by `cat -A` in the canonical repo's copy:
- wrapper `<div>`s at 8 spaces, lines 226 and 240
- headings at 10 spaces: line 227 `<h2>Uncommitted local build SHA-256</h2>`,
  line 241 `<h2>GitHub repository</h2>`
- render line 886 at 4 spaces: `text.textContent = value ?? 'Unavailable';`
- **File is LF in the working copy** despite `file` reporting CRLF. Build LF anchors.

## Standing rules that still apply

- Never push. Canonical `main` is 40+ commits unpushed at Vincent's request.
- Never move `main` during a live run.
- Keep pipeline artifacts out of the repo.
