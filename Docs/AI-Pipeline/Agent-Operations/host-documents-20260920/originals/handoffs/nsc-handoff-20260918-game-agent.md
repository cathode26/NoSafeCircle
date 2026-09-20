# Game Agent handoff — 2026-09-18

Predecessor session: `bcf148aa-0ed4-4ef6-be4c-8104b5587e30`. Retired at 54% context (544k/1M, 463k of it messages).

**Living detail lives in `C:\NSC\agent-state\game-agent.md`.** This file is the entry point: what will hurt you, what is true right now, and how the job is actually done. Where the two disagree, re-derive from the repo — see the last section.

---

## 1. READ THIS FIRST — a trap that will break main

**DO NOT approve or integrate NSC-007's registered candidate `ce1e2283`.**

```
branch assistant/NSC-007 tip : ac87fd00   <- the fixes. EditMode 9/9, PlayMode 36/36
REGISTERED candidate         : ce1e2283   <- contains a NON-COMPILING test (error CS1061 x2)
record status                : awaiting_human
```

`integrate` acts on the **registered candidate**, not the branch tip. Verified in source:
`Pipeline/AssistantControl/source_update.py:86` gates on `candidate.get("commit") != expected_candidate`,
and `integrate` (`review.py:240`) takes no `--candidate-commit`. It is a bare fast-forward with **no compile check**.
Approving this lands code that does not compile onto main and breaks the Unity baseline for every other task.

I created the divergence by committing the fix **on top of** the registered candidate. There is no documented way
to re-point a registration: `register-restored-candidate` refuses a differing candidate
("an existing candidate differs; retained for inspection") and I never found the step that replaces it.

**NSC-007 is NOT decomposed.** At HEAD: `decomposition_children: None`, `execution_scope: needs_execution_decomposition`.
The Decomposition Agent's "review_ready, 3 children" meant a candidate **proposing** three children;
`apply-decomposition` has not run. **`review_ready` is not applied.** I got this wrong in the first version of this
warning, which had the effect of telling a successor to relax about the very trap it exists to prevent.

Both of those were found by read-only successor simulations, not by me.

---

## 2. State right now

**Nothing of mine is running.** No crew, no Unity, no containers, no subagents.

**NSC-097** (Doorway Opening Seal and Door Art State Binding) — the live task. Contract revision 3, landed at
**`cb91d32a7`**. Two crew runs tonight, neither a timeout, both ending without a candidate:

- Run 1 `task-orch-nsc097-20260918-1` → **BLOCKED**. Real contract gap: AC-002 wanted runtime state-driven sprite
  binding while only an Editor-only builder was writable. GER fixed it in revision 3 by authorizing one new file,
  `Scripts/DoorStateSpriteBinder.cs`.
- Run 2 `task-orch-nsc097-20260918-2` → **needs_human** after both attempts. Validator 2's single finding: all four
  door PNGs are imported as `textureType: 0` at `spritePixelsToUnits: 100`; a correct sprite here is `textureType: 8`
  at 64 PPU. So `LoadAssetAtPath<Sprite>` returns null and the approved art physically cannot display.

**That finding blocks every future run of this task and no crew can fix it.** I tried adding the four `.meta` files
to the scope plan; the pipeline refuses outright: *"existing_implementation_paths must not grant model write
authority to .meta"*. Sidecars are pipeline-owned. The contract lists those metas in `exclusive_resources` while the
crew is structurally forbidden to touch them — a contract/pipeline mismatch that needs GER, and a Unity reimport that
needs doing outside the crew. **This was put to Vincent and not yet answered.**

Record is clean: `prepared`, scope valid, no reservation held.

**Waiting on Vincent, one decision each:**

| Item | What |
|---|---|
| NSC-097 door art | Who does the Unity reimport (me, or Art Director), then a commit needing his go |
| `047e5488f` | Release Agent's CI branch, `ci/add-executioncrew-coverage`. Verified by them, reviewed, ran green on real Windows CI. Merges need **his own** go |
| NSC-046 | Stale admission needs a `--force` settle — his word, not a peer's |
| 11 commits | Unpushed, carrying his real committer email. Nothing pushed all night |

**Held, do not merge:**
- `fix/validator-wall-budget` a7d2fbc7b — an audit **reversed its premise**. The validator runs last with the least
  remaining lifetime, so raising its wall makes it inert. Worse: the test-author raise I recommended and Vincent
  approved (merged `0424e318c`) converted clean role-wall failures into silent lifetime kills. No further budget
  raise should land until there is a version bounded by remaining lifetime.
- `fix/melee-leash-and-spawns-20260917` 68cd3aeee — going to an NSC-015 child. Unity-verified (63/63, 8/8). Keep.

**Unmerged, all needing Vincent's own go. Ledger corrected by the Pipeline Maintainer 2026-09-18:**

| Branch | Tip | Note |
|---|---|---|
| `fix/retired-auditor-test-debt` | ca13f7511 | **Merge this first.** Fixes `execution_crew_smoke_test.py`, which is RED on main since 09-14. **The Release Agent is blocked on exactly this for CI.** Sitting since 09-17. Three commits; the third (`55f61230c`) deletes 41 lines of unreachable auditor code and can be merged separately if the deletion should be decided on its own. |
| `fix/retire-archives-one-shape` | d6f3edd01 | Fixes the two live defects in main: `inspect-result` losing a retired run's receipt, and status/viewer calling a retired run live. Reviewed twice by Fable. |
| `fix/partition-defect-names-itself` | 59d41bf9a | Decomposition partition errors now name which defect fired instead of one lumped string. That ambiguity cost four agents an hour. |
| `fix/codex-jobs` | 7c267ceff | Previously verified by me. |
| `fix/quiet-spawns-product` | 9eed24122 | Previously verified by me. |
| `fix/decompose-on-a-snapshot` | 221e59cdb | Previously verified by me. |
| `fix/crew-resume-interrupted-role` | 671be7e8a | **NOT READY — do not merge.** Fable returned FIX FIRST, five items outstanding; the major one is that Claude max-turns classification sits on a path only reached when the CLI exits 0. |

I have verified none of the three new ones myself — verify the trial merge before landing, as always.

**The NSC-046 repair script is NOT coming and is not needed.** `d6f3edd01` makes `current_attempt` discount a launch
the record itself proves finished, so records retired in the old flat shape read correctly as they sit. Do not wait
for a script and do not hand-edit records. (My earlier text said a script was coming; that is superseded.)

---

## 3. Stale artifacts on disk — do NOT reuse

- **`C:\nscrev\reports\dispatch-nsc097.ps1` is a FOSSIL** (now marked in-file). It copies the pre-revision-3 scope
  plan and uses the 3600s config. Running it reproduces **both** failures already diagnosed. It is the one
  obviously-named artifact a successor reaches for — a stranger test confirmed it would have run it.
- **`nsc097-scope-plan-rev3b.json` was REJECTED** by the pipeline (`.meta` write authority). `-rev3.json` is correct.
  See the `.REJECTED.txt` note beside it.
- **`Pipeline/AssistantControl/CURRENT.md`** describes NSC-042 against a September-5 path. Known stale, no marker.

---

## 4. How a dispatch is actually done

Order that works, learned by hitting all four gates:

```
settle-worker -> retire-worker -> refresh-prepared -> scope -> reserve -> start-worker
```

`scope` refusing with *"worker or candidate work is already underway"* is **correct behaviour demanding an explicit
retire**, not a bug. I reported it as a defect and was wrong. The underlying cause is that `retire-worker` archives
the worker but leaves `launch` behind, so other readers still see a live run.

**Pre-flight before spending an hour of crew tokens:**
1. Contract hash == policy hash **at the live HEAD** (main moved four times in one night).
2. The contract names its gate types.
3. The scope plan authorizes **every file the ACs require** — derive it from `exclusive_resources`, not from reading
   the ACs. Run 1's BLOCK was an empty `new_implementation_paths`.
4. Use `worker-claude-sonnet-long.json` (10800s), never the stock 3600s — a full crew plus a repair cycle cannot fit
   in 3600s. Both NSC-097 runs used the long config and neither timed out; NSC-007 died at 3604s under the old one.

**Traps:**
- **Restore a candidate BEFORE retiring, never after.** Retire leaves a `ready_pending` launch that makes restore
  refuse, and retire has no undo.
- **When a host worker dies the container keeps spending.** Check `docker ps` immediately. Recover the work first
  (`docker exec`, `git add -A`, `git diff --cached --binary`, `docker cp`) — then stop it. Never `docker stop`/`rm`
  a pipeline container by hand; crew workers have a self-service path, decomposition containers escalate to Vincent.
- **NSC-046's record lies.** `status` and the viewer report it live; it is not. Same retire gap. A repair script is
  coming from the Pipeline Maintainer — do not hand-edit records.

---

## 5. How to not be wrong (the part I most want carried forward)

Every error I made in two days came from asserting a conclusion I had not checked. The shapes:

1. **Read stderr, not just stdout.** I redirected them to separate files, read only stdout, saw Unity's own
   `Result: Passed (total=0 ...)` and invented a "VALIDATION PASSED" the runner never printed. Its actual stderr said
   `RESULT FAILURE`. I then told three agents and wrote it into fleet memory.
2. **Re-read the code after a repair.** I twice told Vincent a defect was live, saying "confirmed", having only
   repeated a validator finding that a later repair cycle had already fixed.
3. **Absence of a file proves nothing until you check the writer's actual path.** I concluded evidence was
   "permanently lost" from an empty directory; it was on disk in the crew output root the whole time.
4. **Never trust an agent's summary over the runner's artifacts.** Counts come from `test-results.xml` or the
   runner's own output. A subagent's 36/36 was true — but I only knew because I checked.
5. **"Crew succeeded" is three steps short of "it works":** a compile (no crew role ever compiles its own output —
   expect the test file to break), a scene-builder run, and a real Unity run.
6. **A BLOCKED return is a good outcome.** Twice a role refused to exceed its write authority and reported instead of
   improvising. Cost: a run and no candidate. The alternative is a candidate someone unpicks later without context.
7. **Merges into local main need Vincent's OWN go.** A Release Agent request, a GER relay, or a peer quoting him is
   not it. I learned this by merging on a relayed go and having to disclose it.

---

## 6. What a handoff cannot carry

I built a corpus of every request Vincent made — **145, at `C:\nscrev\reports\game-agent-job-corpus.md`** — and had a
read-only stranger attempt a mechanical sample.

**78% are under 120 characters. 31% open with a bare deictic** (`Go`, `gi`, `no`, `ok`, `yes`). Result: 3 actionable,
2 actionable-with-assumption, 3 impossible.

The impossible ones split into two kinds, and the distinction matters more than the count:
- **Unanswerable in principle.** *"Well that sucks"*, *"Unless you think its fun"*. No document can pre-transcribe
  the next live exchange. Do not try to fix these; ask.
- **Answerable, and my handoff was simply wrong.** *"NSC-007 is being decomposed"* — a sibling document had it right
  while mine asserted the opposite, **in the correction block written to be trusted most**.

Highest blast radius in the whole corpus: *"Just delete the changes I think"*. Plausible referents include a
do-not-merge branch holding Unity-verified work and a scratch clone holding the only copy of a fix. **Never act on a
delete whose referent you inferred.**

---

## 7. Open ideas and never-built (from the transcript digest)

Digest: `C:\nscrev\reports\agent-recovery\game-agent-20260918-0358-bcf148aa.md` (134 messages, 3 compactions).

> **CORRECTED 2026-09-18 by the successor session.** The "OPEN, never followed up" item below is
> **wrong on its facts**, and it was wrong when written. The viewer's new-task responsibility **is**
> documented: `nsc-viewer-agent-guide.md` section 4a "Task state and new-task intake (Vincent,
> 2026-09-17)", lines 118-138, and `nsc-agent-directory.md` lines 31 and 85. The contact with the
> Documentation Agent has now been made and they confirmed it. The false negative came from grepping
> the concept's name — the docs say **"new-task intake"**, never "task creation". Same class as
> [[prove-a-type-absent-by-content-grep]]. The rest of this section stands.

- **OPEN, never followed up:** Vincent asked me to check with the Documentation Agent whether the viewer's
  task-creation responsibility got documented. Verified on disk — neither the viewer guide nor the agent directory
  mentions it. I have no record of making that contact.
- **LAPSED:** the SuccessfullTasks archive. `C:\NSC\SuccessfullTasks\` has 7 entries; **NSC-069 is missing** though it
  reached `conformant` and my own state file recorded the archive as owed. The mechanism was built; the habit stopped.
  A board row saying "archive X" proves it was asked for, not that it happened.
- **Informal only:** "Integration Steward" as a title. It lives in memory and in how I work, not in the directory row.

---

## 8. Where truth lives

Re-derive rather than trust, including this file.

- `C:\NSC\nsc-fleet-state.md` — current fleet state. **Nothing in my documents referenced it; a stranger had to find
  it alone.** Read it.
- `C:\NSC\agent-state\game-agent.md` — my living detail.
- `C:\nscrev\reports\nsc007-salvage\RESULTS.md` — the NSC-007 measurements, authoritative over any summary.
- `C:\NSC\CLAUDE.md`, `C:\NSC\nsc-agent-directory.md`, the memory index.
- Task truth: `git show HEAD:Tasks/NSC-###.yaml`. Never read files under `C:\NSC\NSC\NoSafeCircle` with a Read tool —
  it pulls in a very long nested CLAUDE.md.

Conformant count: I say 16 of 95, fleet-state says 17. Probably NSC-069 landing in between; I never reconciled it.
Trust fleet-state.
