# Codex mid-development review: blockers for the NSC-1165 decomposition work

Relayed by Vincent on 2026-09-13 at about 21:35 UTC. It answers `C:\nscrev\reports\mid-dev-review-revision-review-20260913.md` (snapshot `review/revision-review-mid-20260913` = `ce9ce13`). This is binding for the team.

## Keep

Keep the bounded author → independent reviewer → one revision design and its three-call cap. Do not simplify that away.

## Blockers to fix before the decomposition work is called complete

1. **Outer timeout from the effective budgets.** Compute AssistantControl's outer timeout from the effective configured budgets: `author + reviewer + max(author, reviewer) + safety margin`. The current 3600-second limit can kill a valid three-call run.
2. **Advisory-only pass.** Make AssistantControl accept producer-valid `pass` results that contain advisory-only findings. Continue rejecting any blocking finding.
3. **Evidence depends on context.**
   - Explicit synthetic/gauntlet fixtures may produce children with empty `gdd_evidence`.
   - Real game decompositions must give every child valid committed GDD evidence, inherited from the selected evidence or cited directly.
   - Do not make empty selected evidence a blanket production exemption.
4. **TaskGraph fixture.** Repair the invalid checked-in TaskGraph fixture resource partition, so the D1C and local-apply regression suites execute.
5. **needs_human identity checks.** Strengthen the `needs_human` revision-review identity checks using the existing review-ready authentication fields, without granting apply authority.
6. **Whole-stack AssistantControl tests** covering:
   - both valid three-call shapes;
   - an advisory-only pass;
   - the derived timeout;
   - authenticated revision evidence;
   - synthetic no-evidence success;
   - real-task no-evidence rejection.

## Delivery

- Run the revived regression suites and `git diff --check`.
- Report exact commits, test counts, and any remaining failure.
- Keep commits separated by coherent ownership. Do not squash them just to shorten the history.
