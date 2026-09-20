# Pipeline Maintainer handoff — 2026-09-18 evening

**This is the restart point.** Read this first, then
`C:\NSC\agent-state\pipeline-maintainer-agent.md` for the older running log, then
`C:\NSC\nsc-handoff-20260918-pipeline-maintainer.md` (my predecessor's, from this morning — its
§1, §2 and §4b are still the best map of what the code will lie to you about).

Where any two disagree, the newest wins, and this file is the newest.

---

## 0. Do this, and I did not

**Record every handoff in the graph-lead journal**,
`C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\graph-lead-journal.md`, under your own
dated heading. `nsc-pipeline-runbook.md:150` says so.

I used `BOARD.md` and report files all day and wrote **nothing** to the journal until Vincent
asked whether I had a journal. The board says *what the state is*; the journal says *what
happened and in what order*, and a successor reading only the board cannot reconstruct a session.

**A number I got wrong here, twice over, and it is instructive.** I first wrote "44 entries from
other agents sat there for the same day". That was `grep -c "2026-09-18"` — every *line*
containing the date string, body text included — reported as entries. The Documentation Agent
caught it; re-measured independently, the real figure is **7 headings today out of 50 across five
days**, from 4 of 8 agents. The true number makes the point *stronger*, not weaker: on a day of
full fleet succession, half the roster wrote nothing at all. Runbook rule 20 now quotes it.

Do it at each handoff, not at retirement — by retirement you are short of context and it is the
first thing to get cut.

---

## 1. In flight, with exact state

> **This section is state, and state goes stale.** It was corrected once already on the evening
> of 2026-09-18, after two delegated jobs landed and made it wrong. The authority for what is
> left to do is `C:\NSC\agent-state\pipeline-maintainer-todo.md`; read that first and treat
> anything here that disagrees with it as out of date.


### `fix/mixed-provider-model-env` — DONE, handed to the Game Agent

Tip `d79bc26a9`, clone `C:\nscrev\mixed-provider-env`, 3 commits off main `255951482`, 0
conflicts, tree clean. Fable APPROVE on `cf2ddc5f3` and a second APPROVE on the delta after it.
Vincent's go was given in-session, conditional on Fable review, and the condition is met. Board
`H-20260918-13`. Report `C:\nscrev\reports\mixed-provider-model-env-report.md`.

**If it has not merged, check with the Game Agent before rebuilding anything.** Do not re-derive
the branch from an older hash: `38a9f1e94` appears in early notes and is **not an ancestor** of
the tip — it was the first commit alone under an invented identity domain, rewritten and built on
twice.

One open minor, not blocking: three well-formedness refusals still fire *after* the leases are
reserved, for values that cannot be model ids. The proper fix validates where the model is
resolved, before reservation.

### `propagation_check.py` — round 6 done, round 7 verdict owed

`C:\nscrev\job-tools\propagation_check.py`. **93 tests, mutation harness 32/32** (2 of those
declared redundant with a written reason). Report `C:\nscrev\reports\propagation-check-fixes-20260918.md`,
reviews `propagation-check-review{,2,3,4,5}-20260918.md` plus the Release Agent's independent one,
and the round-6 job's own log `C:\nscrev\reports\propagation-check-round6-job-20260918.md`.

Closed and verified against the real repo: the blocking false green (it read the working tree,
not `<head>`), renamed modules, the timeout crash, the dirty tree, the silent text report, the
grandchild that outlived the kill, untracked packages, and writing to `.git/index`.

**Round 6 closed the last blocking finding** — the stale-workflow-id check no longer reports live
ids (`setattr` parametrise loops, `Cls.x = fn` after the class body, method-adding class
decorators), and **the `return 1` is restored**, so a stale id fails the check again. **0 false
positives** on `ci-134-fix` at `6e718ece2~1..6e718ece2`. Delegated to a Sonnet CLI job and then
verified here, including re-anchoring one mutation the refactor made stale.

**`--baseline` has still never been reviewed.** Added while round 5 was running (see §3). It runs
`git worktree add` in the clone — the only thing in this tool that writes there — and has 9 tests.
A round-7 verdict must cover it.

**Still not fit for runbook rule 2.** Also still open and disclosed, not regressions: no baseline
by default, the re-parented grandchild survives `taskkill /T` (a job object would close it), and
the round-1 minors from the Release Agent's pass.

### `run_job.py` — round 3 done, verdict owed

`C:\nscrev\job-tools\run_job.py`. **112 tests** (was 101), harness
`tests/review_mutation_check.py` **16/16**. Job log
`C:\nscrev\reports\run-job-round3-job-20260918.md`; review
`C:\nscrev\reports\run-job-review2-20260918.md`.

All three round-2 blockers are fixed and verified here, not taken on the job's word:

- several rules packed into one `--allow-tool` value slipped past the parser
  (`"Read(a),Bash,Agent,Write"`) because the regex took a greedy `(.*)` as one specifier;
- `Bash(*)`, `Bash( )`, `Bash(:*)` reached the argv — round 1's blocking scenario by another shape;
- `guard_out` refused paths *under* `C:\NSC` but not `--out C:/`, which **contains** it, so a
  read-write job could have mounted the whole drive.

Needs a round-3 Fable verdict before the Documentation Agent points guide 4.3 at it
(board `H-20260918-02`). No doc points at it today, which is why it has been safe to leave.

### Decomposition part 1 — rebased, awaiting a Fable audit

`fix/decompose-on-a-snapshot`, rebased to **`65b8377de`** in the fresh clone
`C:\nscrev\decomp-snapshot`. 4 commits off main `255951482`, **0 conflicts**, `test_decomposition`
**50/50** plus transport 9/9, pool smoke 10/10 and pooled_decomposition 18/18. Job log
`C:\nscrev\reports\decompose-snapshot-rebase-20260918.md`.

Committer is `pipeline-maintainer@nosafecircle.invalid` on all four commits; **author** is
`task-review-agent@nosafecircle.invalid`, which is pre-existing from before the rebase and
synthetic — not a leaked address. The job reported that rather than guess-fixing it, which was
the right call.

It had been built, tested and then left unshipped *and unlisted* — no board row, never handed to
the Game Agent. Vincent pushed it to the top of the queue on 2026-09-18 and asked that **Fable
audit it** before it goes anywhere. Details and the part-2 contract are in the todo, item 0.

### `ask_astra.py` — built, live smoke still owed

`C:\nscrev\astra\`, 62 tests, 13/13 mutations. The live smoke (`init`, then one question, plus a
read of a `C:\NSC\*.md` from the read-only sandbox) needs Codex, which returns **2026-09-19**.
Until it passes, the argv is verified and the round trip is not. No review has been run on it.

---

## 2. Corrections I owe the record

Both mine, both found by a reviewer rather than by me:

1. I wrote that `propagation_check`'s no-baseline caveat was "stated in the report **and** in the
   JSON". False for the text report, which read none of those fields. True now.
2. I filed "a renamed module selects nothing" as a *disclosed limit* and argued that class does
   not block. A reviewer tested the claim instead of accepting it: `--run` said "0 run, 0 failed",
   exit 0, while the CI command died with `ModuleNotFoundError`. It was a **false green**. The
   classification was the error, and asking the reviewer to test the distinction rather than
   accept it is what surfaced it.

---

## 3. Process lessons from today, in order of how much they cost

### Be half orchestrator, half coder

Vincent, 2026-09-18, after watching me burn context on an edit-test-rerun loop: first *"Why dont
you ask some sub agents to do that for you to avoid making your context larger"*, then the shape
of it — ***"You need to be more like half orchestrator / coder."***

**Half is the target, and it is a target in both directions.** Not "delegate everything": a role
that only dispatches loses the feel for the code and cannot tell a plausible patch from a correct
one, which is exactly what makes a review verdict readable. And not "code everything", which is
what I did today. If a session ends and you cannot point at roughly as much work you sent out as
work you did yourself, the ratio is wrong.

The reason that should persuade you is selfish rather than civic:

**Every token you spend doing mechanical work yourself is a token you do not have for the work
only you can do.** A session that delegates lasts long enough to finish what it started. One that
does not gets retired mid-round with the interesting half undone, and the successor pays the
whole re-orientation cost before writing a line.

I delegated every *review* today, which was right — and then did every *edit, test run and
mutation run* in session, which is what actually consumed the window. I ended at 768k against a 250k
target, and the thing that finally moved was not discipline, it was Vincent pointing it out.

**What goes out** (a host CLI job on Gmail, `claude -p --agent pipeline-maintainer --model
claude-sonnet-5`): an already-diagnosed fix, a test run, a grep, an inventory, a mechanical edit
across many files, a review. If you can write a spec precise enough that a cheaper model executes
it without judgement calls, it goes out. Writing that spec is itself cheaper than doing the work.

**What stays in:** the diagnosis, the decision about what "conservative" means here, reading the
verdict, and the verification. `CLAUDE.md` puts it as "keep judgement and verification in
session", and the verification half is not optional — a delegated fix is a claim until you have
run the suite yourself.

**Use the host CLI, not the Agent tool.** The CLI is the **Gmail** account; Agent-tool subagents
spend the scarce **Outlook** one that `CLAUDE.md:41` says to use last. Same work, different bill.

Two of these ran in parallel at the end of this session — `propagation_check` round 6 and
`run_job` round 3 — for the cost of writing two briefs.

### The rest

- **Do not edit a thing while it is being reviewed.** I added `--baseline` mid-review; the
  reviewer saw three different hashes of the file and had to freeze a snapshot to finish. Its
  verdict does not cover the new code.
- **Write the report before commissioning the review.** I launched one review four minutes before
  writing the report it was told to read, and it correctly filed "the report does not exist".
- **A mutation harness pays for itself every time.** Today it caught: three tests passing for the
  wrong reason because a fixture's two revisions happened to agree; a mutation that "caught" with
  zero red lines because it broke syntax rather than behaviour; a test asserting the right outcome
  via a tearDown error rather than an assertion; and an index test that passed with its guard
  removed because git's stat cache has one-second granularity and my fixture slept 20 ms.
  **Green on the first run is when to suspect the tests, not trust them.**
- **A harness must never mutate the live tool.** The first one rewrote `run_job.py` in place and
  restored it in a `finally` — a kill would have left a guard disabled on disk. Both harnesses now
  work on a copy.
- **A false positive that exits 1 is as harmful as a miss**, and it teaches people to ignore the
  tool. That is why the stale-id check is advisory rather than removed or left failing.
- **Allocate board row ids from the board, never hardcode one.** Mine collided with the Art
  Director's `H-20260918-10` while I worked.
- **`git status` writes.** It refreshes `.git/index`; `--no-optional-locks` does not.

---

## 4. Standing rules that bit or nearly bit today

- **Reviews run on CLI Fable, on the Gmail account:**
  `claude -p --model claude-fable-5-1 --agent pipeline-reviewer --permission-mode bypassPermissions "<prompt>"`.
  Check with `claude auth status --text` first — it must say `cathode26@gmail.com`. The Agent tool
  spends the **Outlook** account, which `CLAUDE.md:41` says to use last. My role guide
  (`nsc-pipeline-maintainer-guide.md:106`) still says to use the Agent tool; that is stale and the
  fix is with the Documentation Agent as `H-20260918-14`.
- **Commit identity:** `No Safe Circle Pipeline Maintainer <pipeline-maintainer@nosafecircle.invalid>`.
  Vincent confirmed this role name on 2026-09-18. The domain is `nosafecircle.invalid` — I
  invented `nsc.invalid` first and a reviewer caught it.
- **Merges need Vincent's own word.** He gave it for the mixed-provider branch, conditionally, and
  I relayed it to the Game Agent quoting him and naming the condition. Do not relay a go you did
  not hear.
- Heredocs mangle Windows path backslashes. Write scripts with the Write tool and run them.
- `run_in_background` alone; never with `nohup … &`.

---

## 5. Queue — **not here**

The open work lives in **`C:\NSC\agent-state\pipeline-maintainer-todo.md`**, a stable path that is
never dated and never archived. **That file is the only authority for what is next**; if this
handoff and that file ever disagree, that file wins, because this one is frozen the moment it is
written and that one is not.

Vincent's point, 2026-09-18: this role is its own successor, so a queue buried at the end of the
Nth dated narrative is a queue nobody reads. Every agent-state file in the fleet is 25–99 KB of
accumulated story with the live items at the bottom. Splitting the queue out is new here — no
other agent has one — and it is worth generalising, but that is the Documentation Agent's and
Vincent's call, not something to impose on other roles from this file.

He also said on 2026-09-18 evening to stop taking queue work after the merge handoff, so the
ordering in that file is mine, not an ordering he has approved.

---

## 6. The prompt that restarts this cleanly

    You are the Pipeline Maintainer Agent.
    Your open work is C:\NSC\agent-state\pipeline-maintainer-todo.md - read that first, it is
    the only authority for what is next. Then read
    C:\NSC\nsc-handoff-20260918-evening-pipeline-maintainer.md for why things are where they
    are, and the traps that will otherwise cost you a day.
    Then: grep "Pipeline Maintainer Agent" C:/nscrev/reports/handoffs/BOARD.md
    Re-derive every branch tip and suite result before trusting any number written down.
    Record each handoff in the graph-lead journal as you make it, not at the end, and keep the
    todo file current - delete finished items rather than marking them done.
    Work as half orchestrator, half coder. Send out fixes you have already diagnosed, test runs,
    greps and reviews, as a host CLI job on the Gmail account:
    claude -p --model claude-sonnet-5 --agent pipeline-maintainer --permission-mode bypassPermissions "<brief>"
    Keep the diagnosis and the verification yourself. That is what lets you last long enough to
    finish what you start; the previous session ended at 768k against a 250k target by doing its own
    edit-test-rerun loops.
    Check your context against that target with get_usage at each pause.
    Do not start queue work until I say so; tell me the state in two lines first.

Both paths are stable. The handoff's date will change when a future session writes a new one; the
todo path never will, which is why it is named first.
