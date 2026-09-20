# Running the pipeline: local versus production

One page. Everything runs from the checkout root:

```
cd C:\NSC\TenTaskFinalIntegration-20260905
```

`NscRun.cmd` wraps the scripts in `Pipeline\TaskReviewAgent\` (details in `OPERATOR_RUN_SCRIPTS.md` there). The viewer for either mode is http://127.0.0.1:8813.

## Before any run (both modes)

1. Docker Desktop running.
2. Claude login inside Docker not about to expire (the launcher refuses with < 30 min left):
   ```
   docker compose -p nosafecircle run --rm -it claude-exec claude
   ```
   type `/login`, finish in the browser, `/exit`. Good for a few hours.
3. The checkout is clean and on `main` (`git status` shows nothing). The launcher refuses a dirty checkout.
4. No scheduler is alive from a previous run (the viewer's architect line says "exited", or `NscRun.cmd status`).

## Which mode

| | Local rehearsal | Production |
|---|---|---|
| Use it for | **Getting game code written.** Fast loop, nothing leaves your machine. | Demonstrating the full audited path with GitHub Issues and human PASS. |
| GitHub | Never touched (a fence refuses `gh` and `git push`). | Issues per task, branches, merge gate, `main` pushed by the pipeline. |
| After the crew | Candidate committed into the run's own source, then integrated serially. Auto-accept by default; NSC-042 is always held for you. | Commit, push, gate (merge main + Unity validation), your PASS on the Issue, possible re-validation, delivery evidence, PR, merge. |
| Your review | Open the result in Unity and play it. Merge into your real repo by hand when a batch is good. | Post the PASS block on each Issue. |
| Time per small task | ~5 min crew, integration seconds. | ~5 min crew, then gate, then you, then delivery: 15–30 min and several polls. |
| Fragility today | Low. | Medium: every step after the push has a strict check; see `handoff-20260909.md`. |

Recommendation until the game ships: **local for real tasks, production only for the demo.**

## Local rehearsal, in place ("start-here")

```
.\NscRun.cmd viewer                         # persistent viewer on 8813 (local mode)
.\NscRun.cmd start-here -TaskId NSC-123,NSC-124     # or press Start on the page
```
- `-TaskId` scopes the run; without it the nine-task gauntlet scope runs. Three to five real tasks per run keeps reviews short.
- Auto-accept is on by default. `-DisableLocalCandidateAutoAccept` holds every task at "local review ready" instead; NSC-042 is held regardless.
- Run state lives under `C:\NSC\TenTaskFinalIntegration-20260905-Checkouts\.task-review-agent\local-rehearsals\<run-id>\` (`checkouts\NSC-<id>`, `crew-output`, `local-state.json`).
- **Taking the result (start-here):** accepted candidates are committed straight onto your checkout's current branch as `Local accept NSC-<id>: <candidate commit>` commits. Nothing to fetch. Build and play in Unity; if a batch is wrong, `git revert` its accept commits; when it's right, push `main` (only while no run is live).
- The other local form, `.\NscRun.cmd start` (not in place), clones the release into `C:\NSC\TenTaskFinalIntegration-20260905-Runs\<run-id>\Source` and integrates there instead; fetch from that folder to bring the result over.
- Stop: page button, or `.\NscRun.cmd stop` (`-Force` to kill). Reset (deletes the run and its Docker project): `.\NscRun.cmd reset -Force` after a stop. Docker leftovers: `.\NscRun.cmd prune -Force`.

Known local sharp edges: a stopped crew leaves a dirty checkout; delete `checkouts\NSC-<id>` under the run before restarting that task. The fresh-seed check refuses a synthetic task whose output file already exists (real game tasks are unaffected).

## Production ("start-production")

```
.\NscRun.cmd viewer -Production             # nine tasks enabled, human review on
```
Press **Start run** on the page (or `.\NscRun.cmd start-production -TaskId NSC-042 -HumanReview`). `-AutoApprove` (viewer) or omitting `-HumanReview` (command) turns the synthetic approver back on, which auto-passes the synthetic tasks; NSC-042 always waits for you.

When a node says "Task Needs You", open its Issue and post the block from the handoff comment (commit prefilled):
```
## Human validation result

Result: PASS
Tested commit: <already filled in>

Completed steps:
- Reviewed the recorded commit.

Notes:
Looks good.
```
No label changes needed. Decomposition parents (898, 1007) ask for `## Decomposition application result` / `Result: APPROVE` / `Reviewed plan_id: GDP-...` instead. If main moved since your PASS, the task asks once more for the integrated commit.

Rules that are not optional in production:
- **Never pull or push `main` while a run is live.** Stop, wait for "exited", then update, then Start.
- **Resetting a task is four deletions:** its Issue, its `nsc-<id>-...` branch, the hidden refs under `refs/nsc/claims/` (`gh api repos/<owner>/<repo>/git/matching-refs/nsc`), and its checkout folder. A closed "complete" Issue makes the next worker exit in one turn.
- A parked task (blocked three times) stays parked until the next run; usually its checkout needs deleting first.

## Troubleshooting, fastest reads first

- Page says "Run failed": `launch-logs\<run-id>.stdout.log` bottom, then the run's `events.jsonl` last lines.
- A task blocked: `outputs\NSC-<id>\<newest scheduler-...>\progress.log`, the `[BLOCKED]` line says why.
- Nothing starts: credentials (see top), dirty checkout, scheduler still alive, or the port 8813 viewer is from a different mode (`.\NscRun.cmd viewer-stop` then start it again).
