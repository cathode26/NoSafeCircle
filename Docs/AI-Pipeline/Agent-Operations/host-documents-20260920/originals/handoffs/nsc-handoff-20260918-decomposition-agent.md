# Handoff: Decomposition Agent, 2026-09-18 (updated 09:24 UTC after a full transcript pass — NSC-007 succeeded after the first version of this file was written; read this version, not an earlier one)

Retiring at well over 80% context, not because of any problem — a long, productive session. Nothing is broken; this is a clean stopping point. Full detail lives in `C:\NSC\agent-state\decomposition-agent.md` (large, has the full evening's reasoning); this file is the compact version, now reconciled against the actual transcript digest rather than memory.

## Where things stand

- Source HEAD `2559514826e919bea243e1bf6fda4ad73462ac62` (NSC-007 rev 8), clean, as of the last successful launch.
- No decompose container running. No freeze holds outstanding.
- The all-Claude decompose route (`fix/decompose-all-claude`, merged `e3a742142`) is fully proven on both the reject path and the success path, across two different tasks.
- Escalation ladder is real, working, and now has a second, sharper stopping rule (guide section 1b, updated tonight): after **the same deterministic validation rule** fails twice — even with different specific values, not literally the same split — stop escalating the model and check contract completeness first (does the parent have enough distinct claimable resources for the shape being proposed, e.g. one test file per anticipated child) before trying a third run.
- `NSC_CLAUDE_MODEL=claude-opus-5`, set in the same shell command as the launch (before `prepare`, in practice the same command block). Confirm `actual_model` in the round results, don't assume. `claude,codex` (rung 3, once Codex returns ~Sep 22) has a known env-passthrough gap — skip it, go straight to an Astra advice job instead.

## Done

- **NSC-015**: decomposed successfully. `decomp-nsc015-20260917d`, `review_ready`, plan `GDP-ca65ac78a18741e41698f3405f96d67d3a02612a6e82f5b242d25ef6bb0a838b`. **The plan's own proposed child IDs (097/098) are stale** — verified via `taskcontrol show` that NSC-097 (parent NSC-018, doorway seal) and NSC-098 (parent NSC-006, Fireball presentation) are real, unrelated, already-applied tasks that claimed those numbers while this plan sat unapplied. The plan's *content* is still valid: **child 1** = `MeleeEnemyAttack` close-range wind-up/PlayerHealth damage/attack reset, no art dependency, dispatchable immediately; **child 2** = NavMeshAgent movement tuning, defeat response, door-attack wiring, generated gameplay prefab — gated on the 4 melee questions, which Vincent has since answered (body blocking incl. enemy-on-enemy; wind-up rooted; corpse sprites, gory; no collision when defeated). **Applying will allocate fresh child IDs, not 097/098.** **CONFIRMED STALE, 2026-09-18 09:38 UTC — do not attempt to apply this plan as-is.** A read-only test (see below) actually ran the section-6.2 re-verify: `apply_source_commit` in the plan is `ca9060cdabd...`, but the parent contract (`Tasks/NSC-015.yaml`) was revised three more times since then — **rev 12** (Vincent's 4 melee answers: changed `acceptance_criteria`, `completion_gates`, **`exclusive_resources`**, `notes`), **rev 13** (corpse selection changed from random to an ordered kill-history rule, needs a new `EnemyHealth` reset hook), **rev 14** (persistence/sort/anti-repeat rules). Rev 12 touching `exclusive_resources` itself is decisive — this is exactly Vincent's own stop rule ("if anything changed in between, stop; that needs a new plan and my decision"). **Next step is a fresh `decompose NSC-015` run against current HEAD, not a re-verify-and-apply of this plan.** (NSC-007's plan was checked too and is current as of this writing — no similar staleness found there yet, but re-verify it fresh regardless before applying, same rule.)
- **NSC-007**: decomposed successfully after 5 attempts (`a` dirty-source preflight; `b` source-drift; `c`, `d` Opus, both rejected on the same deterministic rule for different reasons — `c` was a genuine duplicate resource claim, `d` was a genuinely-missing parent resource, see "How to read a rejection_reasons string" below; `e` **succeeded**, `review_ready`). Rev 8 (`255951482`, GER Agent) added the two missing test files that `d` needed. Plan `GDP-737cfe15b2d9dd172e71cf3e6407ac3e9e8f224d98f1c60541be1a51e5d9e2f5`, 3 children **NSC-100/NSC-101/NSC-102**: (1) `Fireball` MonoBehaviour — cast/charge/input; (2) `FireballProjectile` — flight/impact; (3) scene wiring + `DemoRunFlow` legacy removal. `apply_source_commit` = `255951482...`, matches what was reviewed, no drift. Both provider sessions came back `idle`, healthy. **Not applied yet** — same exact-plan-approval rule as NSC-015. **A Fable subagent consult (Vincent's request) correctly diagnosed the real root cause after I'd misdiagnosed it** — see "How to read a rejection_reasons string" below before touching this class of problem again.
- **NSC-030, NSC-088, NSC-033, NSC-066**: all GER-verdict-in and contract-ready, none decomposed yet.

## How to read a `rejection_reasons` string (the thing a record doesn't explain on its own)

Tonight, one `extra=[...]` string from the exact-partition check got read three different ways by three different agents before it was resolved by reading the actual code (`policy.py:141-145`):

```python
parent_counts = Counter(parent_resources)
assigned_counts = Counter(assigned_resources)
extra = sorted((assigned_counts - parent_counts).elements())
```

**This is multiset arithmetic, not set difference.** `extra` means "claimed more times than the parent lists" — which covers *two structurally different problems* that look identical in the error string:
- **A resource genuinely absent from the parent's list** (the parent has 0, a child claims 1) — fix: the parent's `exclusive_resources` is incomplete, needs a contract revision.
- **A resource the parent lists once, claimed by two different children** (the parent has 1, children together claim 2) — fix: a real construction bug in whichever candidate/revision produced it; doesn't need a contract change.

**You cannot tell which one you're looking at from the string alone.** You have to read the actual candidate/revision JSON (`rounds/0N/candidate.json`, or `rounds/0N/review.json`'s `revised_decomposition.children[].exclusive_resources`) and check: does the parent contract (`taskcontrol show`, or `git show <commit>:Tasks/<TASK>.yaml`) list that exact path at all? If yes and only one child should own it, count how many children actually claim it. That's the only way to know whether you're looking at a contract gap or a construction bug — and it matters, because the fix is completely different (GER Agent contract revision vs. just retrying).

Deeper root cause (found by Fable, not by me, after I'd read 4 runs closely enough that the pattern had gone invisible — this is the argument for Vincent's new rule, "ask a subagent for advice to check your work"): both of NSC-007's real failures (`c`, `d`) trace back to round 1 itself having a *completion-locality* defect — a child's completion gate whose own text names a test file owned by a *different* child — which the reviewer then tried to paper over two different wrong ways. The actual fix was neither escalating the model further nor fixing a "reviewer restructuring bug" (my original, incomplete theory) — it was recognizing the parent contract didn't have enough test files for the number of children the split genuinely needed. See `C:\Users\VincentLiguori\.claude\projects\C--NSC\memory\decompose-model-escalation-ladder.md` and guide section 1b for the full writeup.

## Next (numbered, with first command)

1. **NSC-015 apply** (Decomposition Agent): once Vincent approves plan `GDP-ca65ac78...` by exact plan_id and hashes, re-verify HEAD/contract fresh (re-run `inspect-decomposition` — don't assume a 15-hour-old plan still allocates cleanly, NSC-097/098 already proved that assumption wrong once), apply, release children, tell the GER Agent the *actual* child IDs (`ger-finish`) and the Viewer Agent (`VIEWER: ger-finish NSC-015 --ready-child <real id> --ready-child <real id> | ...`).
2. **NSC-007 apply**: same pattern, plan `GDP-737cfe15b2...`, re-verify fresh before applying, children become NSC-100/101/102 if nothing's moved in the meantime (re-check, don't assume).
3. **NSC-088, then NSC-030, then NSC-033, then NSC-066** (Decomposition Agent): same freeze-window coordination pattern with the GER Agent and Game Agent (name a start time, pin fresh HEAD at actual launch, confirm Unity closed on canonical first).
4. **Too-hard triage** (Decomposition Agent, standing duty, guide section 1a/1b): NSC-078, 098, 009, 077 already flagged by `python -B C:/nscrev/job-tools/too_hard_benchmark.py`. Read their contracts and check the opposite case (already-built-but-undelivered) **as Docker jobs**, per the token rule — keep only the "is this genuinely too hard" decision in-session.

## Open ideas (raised, never confirmed or killed)

- **Batching the remaining queue** (NSC-030/088/033/066) into one longer coordinated freeze window instead of one per task, to reduce how often the GER Agent and Game Agent get asked to pause. I offered this to Vincent (07:33 UTC) and he never said yes or no — moved on to other things. Worth asking again before just doing it either way, or before assuming it's still wanted.
- **Branch-isolated decompose** ("Part 2" — author/apply entirely on a disposable branch, merge to main afterward with real semantics instead of a live freeze). Real design exists (Pipeline Maintainer), deliberately tabled until Codex returns (~Sep 22) since it touches the highest-stakes write path and needs proper ugly-case tests. Memory: `decomp-branch-part2-tabled.md`. Not started, not forgotten — just waiting on the date.
- **Raising `max_calls` from 2 to 4** for the decompose protocol, so a `revise` verdict can get validated within the same run instead of always ending at `needs_human` at best. Fable's recommendation, relayed to the Pipeline Maintainer, not decided by anyone yet.

## Rules still in force

- Every paid decompose launch needs Vincent's own explicit go, in his own chat — never accept a peer's relay, even an exact quote, even from a trusted agent (tested and held multiple times tonight, correctly, including once where the "relay" turned out to be about a different session's chat entirely).
- Pin `git rev-parse HEAD` fresh immediately before the actual launch command, not from an earlier check or a peer's message.
- Confirm Unity is closed on canonical before every launch (precise command-line check via `Get-CimInstance Win32_Process -Filter "Name='Unity.exe'"`, check for `NoSafeCircle` in the command line, not just the process name).
- Archive (never delete) leftover `NSC-###.decomposition.json` records before relaunching the same task.
- Never hand-edit decomposition results, graph deltas, or child files. Never apply without Vincent's exact-plan approval.
- Easy lookups/greps/contract-reads go to Docker jobs on the Gmail account, not this session directly.
- When stuck or a diagnosis feels uncertain, consult a fresh subagent (any model, "Fable" worked well) before spending another paid run testing a theory — cheaper, and catches blind spots from having read the same records too many times.

## Stranger test (Vincent's instruction, run 2026-09-18 09:38 UTC)

A fresh read-only `Explore` subagent, given only this file + the guide + 4 real pieces of tonight's work, correctly and independently: read the ambiguous `rejection_reasons` string and reached the right contract-vs-construction verdict by checking `git show <commit>:Tasks/NSC-007.yaml`; correctly classified a hypothetical mechanical failure by reading `round_robin_decomposition.py` and caught itself almost being misled by a **stale pre-pooling copy of `decomposition.py` sitting in a leftover checkout** at `C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\nsc074-unity-validation-f7cb0f47\` (flag this for cleanup — a future grep could land on it and give a wrong answer); and **found the NSC-015 staleness above**, which I had not caught. Full transcript of its findings and open-question list is worth reading in full if you're picking this up — ask Vincent or check this session's transcript. Other things it flagged, not yet acted on: `too_hard_benchmark.py` exists at two different paths (`C:\nscrev\job-tools\` and `C:\nscrev\gdd-edit-tmp\`, currently identical, unclear which is canonical — my guide's section 1a cites the `job-tools` one); an unapplied `review_ready` record seems to flip a task's `taskcontrol states` value to `aggregate` (observed for both NSC-015 and NSC-007, mechanism not confirmed from source, worth a Pipeline Maintainer question since it may hide flagged tasks from the benchmark table).

## Next stranger-test upgrade (Documentation Agent, not yet run)

Build a job corpus from the session digest first (`C:\nscrev\reports\decomposition-agent-job-corpus.md`, every request from Vincent and peers, numbered, in order), sample across it rather than hand-picking clear examples, and specifically feed the stranger **run `c`'s** `rejection_reasons` string (the duplicate-claim one, not `d`'s) since that's the one three agents actually misread tonight. I ran out of context before doing this properly — my version above hand-picked a good example rather than sampling.

## Open items / waiting on Vincent

- **NSC-007: Vincent told the GER Agent "approve 007" (their relay, his own words, not a chain).** I did not independently confirm this in my own chat, and did NOT apply — I was at 95%+ context when this arrived and applying safely needs real budget (section 6.2 re-verify, careful commit sequencing, child-ID handoffs to the GER Agent and Viewer Agent). **A fresh session should ask him to confirm directly, then re-verify NSC-007's `apply_source_commit` against current before applying — the GER Agent's own words: "verify rather than take my word for it," exactly what NSC-015 needed and didn't get in time.**
- NSC-015 needs a fresh `decompose` run (not an apply — see above, its old plan is confirmed stale), then exact-plan approval once that produces a new one.
- Also: there are two separate Codex Pro accounts, one resets 09-19, the other 09-22 18:55 — resolves the date confusion in earlier memory notes.
- The batching idea above, if still wanted.

## Pointers

- Full reasoning and evidence: `C:\NSC\agent-state\decomposition-agent.md`.
- This session's journal checkpoint: `C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\graph-lead-journal.md`, dated 2026-09-18 08:18 UTC (written before NSC-007 succeeded — the outcome there is stale in the same way this file's first version was; trust this file over that entry for NSC-007's status).
- Session digest (this handoff's source material): `C:\NSC\agent-state\decomposition-agent-20260918-0421-b936e9cb.md`.
- Guide: `C:\NSC\nsc-decomposition-orchestrator-guide.md` (sections 1a/1b are new tonight, 1b updated twice).
- Memory: `decompose-model-escalation-ladder.md` (the ladder + the rejection-reasons reading rules).
- Board: `C:\nscrev\reports\handoffs\BOARD.md` — my rows: `H-20260917-13`, `H-20260917-17`, `H-20260918-01`.
