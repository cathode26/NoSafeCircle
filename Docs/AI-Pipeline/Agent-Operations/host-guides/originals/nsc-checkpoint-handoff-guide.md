# Checkpoints and handoffs: for every agent

Agents on this project keep getting cut off: context full, session limits, Codex quota, laptop hibernation. On 9/13-9/14, four sessions stopped mid-task and their work had to be reconstructed from raw logs days later (`C:\NSC\nsc-codex-0913-0914-digest.md`). This guide makes every stop recoverable in minutes.

---

## 1. Checkpoint triggers

Write a checkpoint (section 2) **before**:
- starting anything that runs longer than about 10 minutes: a crew, decomposition, GER round, Codex job, Unity batch, PixelLab generation;
- your context passing about 70%, or right after an automatic compaction;
- Codex usage passing about 80% of its window, or Claude reporting an approaching limit;
- Vincent saying he's leaving, sleeping, hibernating the laptop or taking it home. A hibernated machine **pauses** every local run and has no internet;
- handing work to another agent or role.

Also write one when you finish a task, park a task, or change a shared rule.

## 1b. Retirement triggers — when to run section 3a

**Retire, do not just checkpoint, when any of these is true:**

**Two thresholds** (Vincent, 2026-09-18: *"a hard limit of 600k and a 250k if it is convenient"*). Check with `get_usage`.

- **250k — the target.** At this point retire **when it is convenient**: at a pause, between tasks, when nothing is mid-flight. This is the
  one that saves money, because **a message costs the receiver's whole context on the wake-up turn** - every turn a fat session takes is paid
  at its full size, and a 650k session costs roughly 9x a fresh one for identical work.
- **600k — the hard limit.** Retire **regardless of convenience**. Not a suggestion: past this you are spending several times the necessary
  cost on every turn, and you are approaching the point where you no longer have the budget to retire *well*. The retirement itself - digest,
  corpus, handoff, stranger test - costs something like 50-100k. **A session that waits until it is nearly full cannot afford its own
  handover**, which is the failure this ceiling exists to prevent.

  At the hard limit you may have to stop mid-task. **Record exactly where the work stands rather than rushing to finish it** - an accurate
  "this is half done and here is the state" is worth more to a successor than a hurried completion.
- **You are switching Claude accounts** - the sidebar does not follow the account, so the session cannot come with you.
- **Your role changes** enough that your guides no longer describe what you do.

**Retire at a pause, not mid-task.** Bring running work to a safe point or record exactly where it stands; do not kill running jobs.
A record-backed role (its state lives in durable records) can retire at almost any idle moment; a judgement-heavy one should wait for a
natural break, because what it loses is reasoning rather than facts.

**One caution nobody has tested yet:** every retirement so far has happened at a clean stop. **The 250k tripwire will not wait for one**,
and the procedure has never been run mid-crew with half-finished edits. If you are the first, say so in your handoff.

**Then run section 3a**, and clear with `clear_session` on `"self"` rather than asking Vincent to create a session - see
`C:\NSC\tools\session\README.md`.

## 2. Checkpoint: the journal entry (always)

Append to `C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\graph-lead-journal.md`:

```markdown
## <yyyy-mm-dd hh:mm UTC> <Role> checkpoint: <one-line purpose>
- Source HEAD: <sha> (clean | dirty: <what>)
- In flight: <task> <kind> run_id=<id> crew_run_id=<id> container=<name> started=<time> log=<path>
- Waiting on Vincent: <exact question / test: folder + commit>
- Done since last checkpoint: <items with commits>
- Parked / unavailable: <task ids + one-line reason>
- Next steps (in order): <1..n, each concrete and runnable>
- Do NOT: <anything a resumer must not touch, e.g. "don't rerun NSC-0xx crew: receipt at <path>">
```

Rules:
- IDs and paths must be exact.
- A resumer must be able to act without your conversation. Don't write "the task we discussed".
- Never edit another role's entry.

## 3. Handoff file (when another session will take over)

If a new agent or session must continue, the Main Orchestrator (or you, if alone) writes `C:\NSC\nsc-handoff-<yyyymmdd>[-<role>].md`. The 9/16 handoff is the model to follow:

- **Where things stand:** HEAD, ahead or behind origin, dirty files that are known churn, running processes.
- **Done:** a short list with commits.
- **Next:** numbered, with owner role and exact first command.
- **Rules still in force:** never push; one branch at a time; stage exact paths; semicolon test filters; and so on.
- **Open items and decisions waiting on Vincent.**
- **Pointers:** journal, reports, memory notes, relevant guides.

Keep it under about 80 lines, and link out for detail.

Also update memory:
- one memory file per durable fact, not per session;
- mark stale memories as historical rather than letting them mislead. On 9/16, three memory notes were wrong: "viewer fix not merged", "22 holds", "Codex out until Sep 19".

## 3a. Writing a retirement handoff (the send-off document)

Section 3 covers a handoff when another session takes over a task. **This section is for retiring a whole role** - when your
context is full and a successor, possibly this same session after a self-clear, continues as you. Learned on 2026-09-17/18 from
seven agents answering "what would your successor lose?", a gap check that found errors in the result, and two passes over a
session's own transcript.

### The three rules that matter most

**Rule zero, and it takes one line: every handoff names the author's todo file, in its opening paragraph.** Vincent, 2026-09-18, instructing the Pipeline Maintainer and through it the fleet: keep a todo, and *"put a reference to the todo in the handoff so they know what they need to work on next"*. The handoff says what the last session **learned**; the todo file says what is **left**. A successor that reads only the handoff must still be pointed at the queue on the first screen, or it will reconstruct a to-do list out of narrative and get it wrong. This is the positive half of the rule in "What not to put in" below - **name the queue, never copy it.**

**1. File as you go. The handoff is the residue, not the record.** Everything durable belongs in its proper home *while you
work*: a rule in a guide, a fact in memory, a decision on the board, a rationale in the contract it constrains. The handoff
carries only what had no home. **The size of your handoff measures how badly you filed**, which is why the record-backed Viewer
Agent needed about 7 KB and the Documentation Agent about 27 KB - a ratio, not a target, and both measured with `stat` rather than recalled.

**2. Write nothing you don't own.** State only what you own and can re-derive by command; everything else is a *pointer* to the
owner's file. One author restating seven agents' state is how a fleet-state file shipped with a wrong line inside the hour, and
how a retirement handoff was wrong at birth in three places. **A stale line is worse than a missing one, because it reads as
current.**

**3. Digest your own transcript before you write. An author cannot write down what it has forgotten.**

```text
python -B C:\NSC\tools\session\nsc_session_digest.py digest --session <your cli session id>
```

The id is the `.jsonl` filename under `C:\Users\VincentLiguori\.claude\projects\C--NSC\`. **Never open the transcript
directly** - they run 1-90 MB. A long session has compacted more than once, so its earliest instructions are no longer in its
context at all.

### The four passes over the digest

| Pass | Where | What it finds |
|---|---|---|
| 1 | Section 2, **oldest first** | Vincent's instructions from before your compactions |
| 2 | Section 2, grep `maybe\|eventually\|later\|we should\|do we need\|what if\|I think we` | **Ideas he raised that were never killed and never built.** Nothing in the system owns "ideas", so they exist in no other record |
| 3 | Sections 5-6, then **check the disk and the records** | What you promised or queued - **and whether it happened.** Two kinds: *artifacts* (a board row saying "build X" proves someone was asked, not that X was built) and **promises to a peer** - "I'll confirm that lands", "I'll check and tell you". **A promise exists only as words in a message and in no record at all**, which is why this pass is the only thing that can catch one |
| 4 | Your own replies | Claims you asserted that were later corrected: who heard them, were they told |

On 2026-09-18 pass 2 found four open ideas and pass 3 found **three of four queued tools had never been built**, each with a
written brief and a board row. Neither was recoverable from memory. Passes 1 and 4 yielded less, because most of that had
already reached CLAUDE.md or memory - **the pass has sharply diminishing returns once you file as you go**, which is the point.

**The control case is worth knowing before you budget time for this.** The Viewer Agent - record-backed, records kept current -
ran all four passes and found **nothing factual new**. It found exactly one thing: a promise to a peer, *"I'll confirm blue
lands"*, never followed up. That dropped promise had left a worker stuck at `ready_pending` for about fifteen hours, probably
holding a lease. **So for a role whose state lives in records, the pass is not for recovering facts - it is for recovering
commitments**, which by their nature were never written anywhere.

### Any inventory a successor inherits must record how it was made

From the Art Director's stranger test: one inventory recorded **what exists**, another recorded **how each item was produced** - the call,
the settings, the seed, the post-processing. **A successor could repeat the second batch and not the first.** An inventory that lists only
results is a receipt, not a method, and the difference is invisible until someone needs to extend the set.

Generalise it: **any artefact list a successor inherits - generated assets, test fixtures, staged files - carries the command and parameters
that produced each item.**

### The one practice that beats any handoff: capture the answer beside the question

**A simulation against 12 real messages scored 4 actionable, 4 actionable-with-assumption, 4 impossible.** All four impossible ones
were the same shape - `yes`, `yes do it all`, `Give yourself 10000`, `what percentage will we save?` - **deictic replies to a turn that
no durable document carries.** State-and-rules documents structurally cannot hold live dialogue, so no handoff, however long, fixes this.

**So fix it at the other end: when he answers, write his exact words next to the exact question, in the decision file or the board row,
at that moment.** Not in scrollback, not in a summary later. A question recorded without its answer, or an answer recorded without its
question, is half a record and the half that survives is the useless one.

This is cheap while the thread is live and impossible afterwards. **Handoff sections that reconstruct decisions from an old transcript
are patches for not having done it** - they work, they cost far more, and they miss whatever the digest did not surface.

### Pass 5: build your job corpus from the digest

**Passes 1-4 recover what you forgot. This one tells you what the job actually is** - and the two are different. Extract every request
you received, from Vincent (digest section 2) and from peers (section 3), into one numbered file in order:

```text
C:\nscrev\reports\<role>-job-corpus.md
```

**The digest truncates its sections by default, so a corpus built from a default digest is silently incomplete.** Sections 3 and 5 keep
only the newest items that fit their budget. **Pass `--scale 5` when you generate the digest** if your session was long - the Viewer Agent
needed it to avoid losing section 3, and the Decomposition Agent, not knowing the flag existed, built its corpus from a retained window and
recorded the truncation as a gap it could not fix. **Check the counts:** if the digest says "140 total, oldest 131 omitted", you are
sampling from nine messages, not 140.

**Then sample across the whole session, not the parts you remember.** The Documentation Agent's corpus held 175 requests from Vincent
and 9 from peers. Measured: **70% under 120 characters, 39% under 60, 17% under 30.** The shortest were `yes`, `land v3`,
`and fireball?`, `So the 3rd room`.

**Two things fall out of it, and neither is available any other way:**
- **The communication profile** (see the section list below) - his shorthand, what a bare `yes` attaches to, what a bare number means.
  Derive it from the corpus, because impressions systematically over-remember the long interesting messages.
- **The exercises for the stranger test.** Hand it a stratified sample of *real* messages rather than scenarios you invent. The invented
  version found a documentation contradiction; **the corpus version scored 4 actionable, 4 actionable-with-assumption, 4 impossible**, and
  found both a live routing defect and the structural fact that a third of real work is deictic and cannot be carried by any handoff.

**A handoff that reads well against invented exercises and fails against the corpus is the normal result.** The corpus is the honest test.

**Two scores so far, and the difference is the role, not the effort.** A judgement-heavy role (Documentation) scored **4 actionable / 4 with
assumption / 4 impossible**; a record-backed role (Viewer) scored **4 / 5 / 1**. The record-backed role's single failure was a method it had
used once and never written down - decoding a viewer legend row that conflates two unrelated states. **Expect roughly a third of a
judgement-heavy role's work to be uncarryable, and expect a record-backed role's failures to be undocumented methods rather than missing
facts.**

### Sections that earn their place

- **How the person you work for *writes*, not just what he wants.** The least documented and most valuable section. Measured on
  2026-09-18: **70% of Vincent's messages are under 120 characters and 17% are under 30** - `yes`, `land v3`, `and fireball?`. **Most
  of the job arrives as fragments meaningless without their thread**, so a handoff that explains only state and rules has the wrong
  shape. Write the conventions: what a bare `yes` attaches to, what a bare number means, how he answers numbered lists, which
  statements about himself are really instructions, and which of his typos have been mistaken for rules. **Build it from your job
  corpus, not from impressions**, and quote him.
- **Failure shapes, not virtues.** "Verify carefully" transfers nothing. *"Read stdout without stderr and you will invent a pass
  that was a failure"* transfers everything. Name the shape.
- **Scar tissue.** Rules that look arbitrary without the incident behind them - a prohibition on rendering one sprite state, a
  file marked not-writable. **A tidy successor deletes these and reintroduces the bug.**
- **Fixes deliberately not made**, and **numbers deliberately left unpinned**. Both are places where the obvious next step is
  wrong. Three agents invented this section independently, which means the system lacks a home for "considered and rejected".
- **Open ideas**, with closed ones marked closed rather than deleted - **a deleted idea returns as a fresh idea at the next
  digest.**
- **Queued but never built**, with the on-disk check done.
- **Outbound claims that proved false**, and whether each hearer was told. Nobody else can reconstruct this.
- **Volatile state as commands, not values.** Print the command that re-derives it; a value goes stale silently.
- **A day-one errata slot** for the successor: lines already false, lines re-derived anyway, lines never needed. **Nothing else
  measures whether a handoff worked.**

### Check your own handoff against the repository before you clear

**Write it, then verify it — the two are separate passes.** The Art Director found three stale facts in its own freshly-written
handoff by checking `git` rather than recalling: a contract revision that had moved on, a second contract it did not know existed,
and a task it believed blocked that was already unblocked. The Documentation Agent's had three of the same class, found by an
outside reader. **Every one was a fact the author had been confident about.**

Cheap checks: `git log -1` for any sha you cite, `ls` for any path, the owning agent's own file for anything about them.

### When a rule contradicts the quote it cites, look for the missing distinction

**A rule disagreeing with its own quoted source is usually not an error in either - it is two facts collapsed into one sentence.**

Worked example, found by a stranger test on 2026-09-18: `CLAUDE.md` said "no Codex until 2026-09-22" while quoting Vincent saying "no more
codex until **the 19th**". This role had already "resolved" it once by picking the later date and treating his words as stale. **Both dates
were right: there are two Codex Pro accounts, resetting on the 19th and the 22nd.** Picking a side hid a real fact and would have idled the
fleet an extra three days.

**So: when a document and its quote disagree, hunt for the distinction that makes both true before you correct either** - and if you cannot
find one, ask rather than choosing. The GER Agent, which found this, was one message from asking Vincent to choose between two dates that
were both correct.

### What not to put in

Anything already in a guide, memory, the board or a contract; **another agent's state**; polished prose. Length is not the
constraint - a 10,000-word handoff costs ~13k tokens against the 650k transcript it replaces. **Non-duplication is the
constraint**, because a copy rots and then contradicts its source.

**And not your work queue.** From 2026-09-18 that lives at `C:\NSC\agent-state\<role>-todo.md`, and a handoff **points at it**
rather than repeating it. A queue inside a handoff is stale by the next session and buried by the session after that - which is
exactly the failure the todo file exists to end. Update the todo file as part of retiring; it is the one file your successor reads
before this one.

### What a successor reads, and in what order — settled 2026-09-18

**Three NSC procedures disagreed about this until a successor dry run tripped over it.** The roster's start prompt said read your
`agent-state` file first and never mentioned a handoff; the self-clear wake line named the handoff and fleet-state only; the generic
Successor prompt named the directory, the newest handoff, a fresh digest and the board. **This is the order. The others are wrong where
they differ.**

1. `CLAUDE.md` and the memory index - loaded automatically, no action needed.
2. **`C:\NSC\agent-state\<role>-todo.md` - your live queue, and the answer to "what do I do next?"** Stable path, never
   dated. **It is the authority for what is next**; a dated handoff is frozen when written, so where they disagree this wins on
   *what to do* and the handoff wins on *what was true*. Added 2026-09-18 on Vincent's instruction; if your role has no such file
   yet, your first act is to write one. Shape: `agent-state\pipeline-maintainer-todo.md`.
3. **`C:\NSC\nsc-handoff-<yyyymmdd>-<role>.md`**, the newest for your title. This is the delta - what the last session learned.
4. Your row in `C:\NSC\nsc-agent-directory.md`, then the guides it names.
5. `C:\NSC\nsc-fleet-state.md` for pointers to other agents - **their** files, never a summary of them.
6. **`C:\NSC\agent-state\<role>.md` if one exists.** It is **not** retired: it is the running log, and the handoff is the delta on top
   of it. If they disagree, the handoff is newer and wins, and you should reconcile them rather than leaving both.
7. Board rows from or to your title, and a digest of your predecessor's transcript if one was not built for you.

**Four files, four questions, and keeping them apart is the point:** the todo file answers *what is left*, `BOARD.md` *what was
handed between agents*, `graph-lead-journal.md` *what happened in what order* (append-only), and the handoff *what that session
learned* (frozen). A queue copied into any of the other three drifts and then contradicts the original.

**A number in an `agent-state` file may be older than the same number in a handoff.** On 2026-09-18 one said "93 tasks / 92 active"
while the other said "75 active implementation, 17 of 95 conformant" - different metrics, never reconciled, and a stranger could not
tell which was current. **Say which metric you are quoting, or don't quote it.**

### A verification command is itself a claim — run it before you write it down

This guide tells you to replace volatile values with the command that re-derives them. **A command that does not work is worse than a
stale value, because it looks verifiable.** The Art Director put a command in its handoff to prove a spend correction had landed; the
command matched nothing, because the documents phrase the figure "132 against 97 printed" rather than the form it grepped for. **It found
that by running its own instructions, not by reading them.**

**Run every command you put in a handoff, from the directory a successor will be in, and paste what it actually printed.** After doing
that it could say "29 of 29 handoff claims verify by command" - which is a far stronger statement than a handoff full of plausible
commands nobody has executed.

**The same applies to staged files.** Its staged death inventory sat one directory above the folder NSC-099 names, so a crew copying the
tree would not have found it. **If a contract names a destination, stage at exactly that path and check it with `ls`** - a tree that is
nearly right fails silently at the one moment it matters.

### Test the handoff on a stranger before you clear

Vincent, 2026-09-18: *"create a subagent, simulate giving it what you would give yourself and see if it can do your job. If it has
questions about doing your job, you know what the document is missing."* **Do this after the document is written and before you clear.**

Launch a cheap subagent, **read-only** - no edits, no messages, no dispatches - and give it exactly what a successor receives: your
handoff, `CLAUDE.md`, your row in the agent directory, the guides that row names, the fleet-state file and the memory index. Then give it
**three or four pieces of real work from your lane** and tell it to stop and log a question wherever it cannot determine something rather
than inventing an answer.

**The deliverable is its questions, not its answers.** Ask it for: what it could not determine and where it looked; what it had to guess;
contradictions between any two documents; anything important but unexplained - a name, an abbreviation, a rule with no reason; and **what it
would have asked you if you were still available.** That last list is the gap in your handoff, stated by someone with no way to fake
familiarity.

**Do not hand it exercises the documents already answer.** The Art Director found two of its four were pre-spoiled that way, and a
spoiled exercise tests reading comprehension rather than the handoff. **Redact the outcome, or pick a decision the documents do not
record** - a judgement call, a taste call, a routing choice with no written precedent. Better still, draw the exercises from your job
corpus (above) so the distribution is real rather than chosen.

**A long list of questions is a successful test.** It means you found the gaps while you could still fix them, which is the entire point of
running it before the clear rather than discovering them through a confused successor a week later.

Three checks now stack, and they catch different things: **an outside review** finds what is factually wrong (it found seven errors in this
guide's own first draft), **a transcript digest** finds what you forgot, and **a stranger doing your job** finds what you never thought to
write down because you have known it for days.

### Then clear

`C:\NSC\tools\session\README.md` has the mechanics. **Prefer a self-clear** (`clear_session` with `"self"`) over creating a
new session: the session keeps its id, so every other agent's saved address still works, and Vincent does nothing. Note that
`nsc_session_digest.py` will not digest the session running it, so **build your digest before you clear**.

## 4. Before an unattended stretch (Vincent sleeping or away)

1. Make sure every running job has its IDs in the journal.
2. Check the Codex quota (Watcher check). If there isn't enough for the planned work, say so **now** rather than failing silently later.
3. **Heartbeats and automations.** If you use one:
   - its prompt says to alert on meaningful change only, to stop launching when quota errors appear, and to post one clear "stopped: quota" message;
   - it has an end time (`UNTIL=`);
   - after the stretch, confirm it is paused or expired.
   - "Poll Gauntlet repair board" stayed ACTIVE for a week after its work ended.
4. Tell Vincent in one line what will run, until when, and what he'll find when back.

## 5. Resuming (new session or after compaction)

1. Read the newest `C:\NSC\nsc-handoff-*.md`, then the journal's newest sections for every role.
2. **Verify, don't trust.** Re-derive state from records:
   - `git -C C:\NSC\NSC\NoSafeCircle status --short --branch` and `log --oneline -5`;
   - `python -B C:\NSC\tools\viewer\nsc_viewer.py status`;
   - `docker ps`;
   - `worker-status NSC-###` for each task listed as in flight;
   - `.assistant-control\NSC-###.decomposition.json` status for decompositions.
3. If a handoff says a job was running and there is no process, container or result, treat it as **unknown**, not failed. Read its logs and records before doing anything. Never rerun a crew whose result might exist (Task Orchestrator guide, section 7).
4. Write a short "resumed" journal entry: what you verified, and anything that differed from the handoff.

## 6. Codex and other external sessions

- A Codex desktop or CLI session that stops at quota leaves its rollout in `C:\Users\VincentLiguori\.codex\sessions\YYYY\MM\DD\rollout-*.jsonl`.
- To recover what it did, condense user and assistant messages and shell commands with a small script, as on 9/16. The digest has the pattern.
- Prefer that the session wrote journal checkpoints, so this isn't needed.
