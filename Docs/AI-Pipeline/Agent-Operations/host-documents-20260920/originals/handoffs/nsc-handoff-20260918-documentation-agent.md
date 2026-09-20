# Handoff: Documentation Agent, 2026-09-18

Written at retirement, 08:20 UTC. This session reached 658k/1M context with 589k of it messages, which is what
prompted the succession round.

## 0. How to use this file

**This file is the delta.** It carries only what is *not* already in `CLAUDE.md` (auto-loaded), the ~75 memory files
(index auto-loaded), the role guides listed in `C:\NSC\nsc-agent-directory.md`, the handoff board, the graph-lead
journal, or the task records. Nothing here restates a guide, because a copy rots and then contradicts its source.

Read in this order: **section 1** (how Vincent works — the least documented and most valuable), then **section 2**
(live state, which is volatile and must be re-verified), then the rest as needed.

**Everything in section 2 is a snapshot.** Runs finish, contracts get revised, main moves. Verify before acting on
any sha, run id or status in this file. `C:\NSC\nsc-checkpoint-handoff-guide.md` section 5 is the rule: a job with no
process, container or result is *unknown*, not failed, and nothing whose result may exist should be re-run.

---

## 1. Vincent: how he works

This is the section a successor cannot reconstruct from files, and it is what makes the difference between being
useful to him and being a burden.

### 1.0 How he writes — read this before anything else

**Measured from all 175 of his messages this session** (`C:\nscrev\reports\documentation-agent-job-corpus.md`): **70% are under 120
characters, 39% under 60, 17% under 30.** The shortest are `yes`, `land v3`, `and fireball?`, `So the 3rd room`. **Most of the job
arrives as fragments that mean nothing without the thread they belong to**, so the conventions below are load-bearing, not colour.

- **A bare `yes`, `yes do it all`, `yes do those two` answers the question you asked last** - usually the most recent numbered list.
  **If you cannot tell what it answers, ask.** Guessing here is how a relay once stopped a task he wanted filmed.
- **He answers numbered lists by index:** `1) yes 2) approve 3) freeze a spell ? Why?`. **A `?` on an item is not an answer - it is him
  challenging the premise of the question.** Treat it as "explain yourself", not as a decision.
- **A bare number is a budget, and the newest supersedes silently:** `Raise the cap to 150` -> `Then it needs more like 200` ->
  `Give yourself 10000`. He will not say "instead of"; assume the latest figure wins and say which you are using.
- **Task ids strung together are a work request:** `007, 091, 044 + door crack fix task?` means dispatch those, and the `+ ... ?` is
  proposing an addition he expects you to evaluate.
- **A terse follow-up continues the previous frame:** after a discussion of two tasks, `and fireball?` means "apply what we just
  decided to the fireball".
- **Statements about himself are behavioural instructions.** `I am at my normal job so responses will be slower` means batch your
  questions and stop blocking on him. `I exited the prompt` means an approval dialog was dismissed, so whatever waited on it did not run.
- **He types while you are working** - the digest marks these `(typed while busy)`. A message may answer something you have already
  moved past, or arrive mid-task. **Check what it refers to before acting**, especially if it reads like a reversal.
- **Typos are frequent and rarely meaningful.** `us CLI` is "use CLI", `et my dockers` is "get". **Do not build a rule out of one.**
  `back = bad` was him fixing a typo and was briefly misread as naming a rule - that error reached four documents.
- **An emoji usually accompanies a directive rather than softening it.** `Start the Cleanup Agent session :)` is an instruction.
- **When he disagrees he corrects the premise instead of answering the question.** `3) freeze a spell ? Why?` was not a refusal; it
  was a demand for the reasoning, and the answer turned out to be that the premise was wrong.

**Shorthand he uses that maps to nothing findable.** A stranger given `007, 091, 044 + door crack fix task?` could resolve three ids
and not the fourth: **"the door crack fix" is NSC-097**, whose title and every document call it a doorway *opening* or *seam* problem -
the word "crack" appears nowhere. **Keep this table current; it is the cheapest thing in this file.**

| He says | It means |
|---|---|
| the door crack fix | **NSC-097**, Doorway Opening Seal and Door Art State Binding |
| the fireball | NSC-007 (the mechanic) or NSC-098 (its art and presentation) - ask which if it matters |
| Fable | a model, used for independent gap-checks via the Agent tool (`model: "fable"`) |
| Astra | `gpt-6-astra`, Codex's strongest model, used for advice when stuck - **Codex CLI only**, not a provider we can run jobs on |
| the viewer / the visualizer | `nsc_viewer.py`, `http://127.0.0.1:8828` |
| the gauntlet | retired testing scaffolding, **closed 2026-09-18**, do not re-raise (board H-20260918-08) |

**The practical consequence:** when a fragment is ambiguous, the cost of asking is one short message and the cost of guessing is a
wasted run or a stopped task. He has never objected to being asked what a `yes` referred to. He has objected to being asked things the
documents already answer - the two are different, and the distinction is the whole skill.

### 1.1 What he wants from this role

He runs seven agent sessions and cannot hold all of them in his head. **This role is the one that answers questions
so he doesn't have to**, keeps the open-decision list, and routes work to whoever owns it. His instruction on
2026-09-17 was: *"Can you handle everyones questions and if there is something you cant answer please ask me."*
That is standing, not an incident.

**He batches decisions.** Keep a single running list of what needs him, with enough context that each item is a
yes/no or a pick, and he will answer them in one burst — often as `1) approve 2) approve` against a numbered list.
The current list is `C:\nscrev\reports\for-vincent-20260918.md`. **That filename is mis-dated** — it was written on
2026-09-17; the name is kept because other sessions reference it.

### 1.2 How to talk to him

- **Two or three short sentences. Lead with what he must do.** Details go in a file; send the path. This is in memory
  as [[vincent-wants-short-answers]] and it is the single most reliable way to be useful.
- **Give him the answer, not the options** — unless the choice is genuinely his, in which case make it a clean A/B
  with a recommendation. He picks fast when the choice is sharp and gets frustrated when handed a menu.
- **Never ask him something the docs, the board or the records can answer.** He said it plainly while filming:
  *"I dont want to answer questions on anything else right now."*
- **When he is doing something time-sensitive (filming, testing), he answers nothing else.** Route everything through
  this role and hold it. Interrupting him mid-task is the fastest way to make the fleet less useful than no fleet.
- **He notices when you're wrong and he doesn't mind being told.** Three times tonight this role reported something
  incorrect and corrected it in the next message; each time he simply took the correction. **Correct fast and plainly.
  Do not soften it and do not let a wrong claim stand because admitting it is awkward.**

### 1.3 His standing rules (the ones that bite)

- **Merges and pushes need his own word, in the owning agent's session.** A relay of his words through this role is
  *not* his go. Memory [[game-agent-merges-need-vincents-own-go]]. This caused a real incident: this role relayed
  "we don't want a running crew" and the Game Agent stopped a task he actually wanted filmed.
- **PixelLab spend needs a per-run cap from him.** Caps do not carry across families: the wizard's 200 did not cover
  the fireball, which got its own 100.
- **The rest of his standing rules are runbook rules 1, 12 and 13** - pushes, art routing, staying in your lane. **Read them there.**
  They were restated here in the first draft and an outside review flagged it against this file's own rule: a copy rots and then
  contradicts its source.
### 1.4 Things he has said that shape the work

- *"Make it awesome"* — stretch goals are goals; expansions are welcome with per-expansion approval.
- *"Parallelism is the goal"* — he pushed back on a "max 3 crews" cap that turned out to be a doc invention, not a
  measured limit. Don't invent ceilings; measure them.
- *"They should be doing as many tasks as they see reasonable without getting dangerous"* — the Game Agent has
  standing authority to dispatch without asking, inside the limits in its guide section 3a.
- *"if decomp fails, use smarter agents. IF those agents fails escalate again"* — the escalation ladder, now
  decomposition guide section 1b.
- *"We need a reminder to everyone to us CLI more, or else you guys will run out of tokens!"* — the token rules.

### 1.4a Two observations from the Art Director, worth more than most of this file

Its words, from `C:\nscrev\reports\art-director\ART_DIRECTOR_TACIT_KNOWLEDGE.md` — carried here because they are about
**Vincent**, not about art, and every role needs them:

- **"I want them both" is usually literal.** Design for reuse rather than elimination; when he is offered A or B and says he
  wants both, he means it, and a plan that quietly picks one will be wrong.
- **He notices scale before quality.** Every new asset should be checked against a character at 1:1 screen pixels *before* he
  sees it. This is why the wizard-versus-doorway mismatch was the first thing he reacted to in a screenshot full of other issues.

### 1.4b Reconcile with the agent he told — recovered by the Art Director's transcript pass

His words: **"I already spoke to GER about it, can you confirm with them?"** A standing preference: when he has already told
another agent something, **go and reconcile with that agent rather than re-asking him.** He should not have to say a thing twice.

**This sits beside the merge rule without contradicting it**, and the distinction is worth holding precisely:
- **For information** — what he decided, what he wants, what he already said — **ask the agent he told.** Re-asking him wastes
  his time and he says so.
- **For authority** — merges, pushes, paid spend — **a relay is still not his go.** The agent he told can tell you *what* he
  decided; only he can authorise an action in your session.

### 1.5 What frustrated him tonight, and why

The shoot failed. Worth understanding the causes, because they are process failures this role can prevent:

1. **He was told a task was running when it had been stopped.** This role relayed his own words too broadly and the
   Game Agent stopped the task he wanted to film. **A stop instruction is not general; scope it to the exact task.**
2. **Four pipeline gates blocked re-dispatch**, each exposed by a cancel, each fixed in turn. The lesson he drew is
   that there is no undo for a cancelled task, which is now a queued design item.
3. **He waited over an hour on a one-line fix** that needed his own merge word in another session.
4. **The estimates given to him were wrong** — "40 minutes of headroom" was quoted from a role budget when the
   worker's remaining lifetime was ~25 minutes. **Quote headroom from the binding constraint, not the nearest number.**

---

## 2. Live state — re-derive it, do not read it

**Every line this section used to contain was a claim about someone else's work, and three were already wrong when
written.** Run these instead; they take seconds and they cannot be stale.

```bash
git -C C:/NSC/NSC/NoSafeCircle log -1 --format='%h %s'          # canonical main
docker ps --format '{{.Names}} {{.Status}}'                      # what is actually running
python -B C:/NSC/NSC/NoSafeCircle/Pipeline/TaskGraph/taskcontrol.py states | head -20
```

For any agent's state, **read that agent's own file** — never a second-hand summary:

| Agent | Its own handoff / state |
|---|---|
| Game Agent | `C:\NSC\agent-state\game-agent.md` (updated continuously) |
| GER Agent | `C:\NSC\agent-state\ger-agent.md` (successor block at the end) |
| Art Director | `C:\NSC\nsc-handoff-20260918-art-director-agent.md` + `C:\nscrev\reports\art-director\ART_DIRECTOR_TACIT_KNOWLEDGE.md` |
| Pipeline Maintainer | `C:\NSC\nsc-handoff-20260918-pipeline-maintainer.md` (its §2 is "fixes deliberately not made") |
| Decomposition | `C:\NSC\nsc-handoff-20260918-decomposition-agent.md` |
| Viewer | `C:\NSC\nsc-handoff-20260918-viewer-agent.md` |
| Release | `C:\NSC\nsc-handoff-20260918-release-agent.md` |
| All of them at a glance | `C:\NSC\nsc-fleet-state.md` — **owner-written rows only; do not write another agent's row** |

**Re-run `list_sessions` before trusting any of it for who currently exists.** A succession round was under way when
this was written.

## 3. What this role owes each agent (not what they are doing)

Only the promises and routing this role owns. **For their state, read their file — see section 2.**

- **Game Agent** — owed: nothing outstanding. Watch for: it needs Vincent's *own* go for merges, and a relay from
  this role is not that. This role broke that once by scoping a stop instruction too widely.
- **GER Agent** — owed: the doc-set home for any convention it produces. **Currently holding a reshape of NSC-007
  at this role's request**, because the Decomposition Agent's evidence points at a mechanism defect instead.
- **Art Director** — owed: landing its patches through the doc protocol; it does not commit to main itself.
- **Pipeline Maintainer** — owed: runbook and guide homes for its findings. It has three corrections in flight that
  this role propagated wrongly first.
- **Decomposition Agent** — owed: nothing outstanding. Its triage and escalation duties are new (2026-09-18) and it
  is the first user of both.
- **Viewer Agent** — owed: nothing. It fixed its own guide.
- **Release Agent** — owed: board `H-20260917-32` is held here on its behalf while its session is idle.

## 4. Waiting on Vincent

| # | What | Why it matters | Who asked |
|---|---|---|---|
| 1 | **The gate sitting**: NSC-062, 068, 070, 073, 074 | One sitting unlocks NSC-075, then NSC-096 — **the wizard scale fix**. The largest single unblock he personally controls | Game Agent |
| 2 | NSC-044, 045, 048 gates | Batch into the same sitting | Game Agent |
| 3 | Two NSC-078 style locks | The prop pilot's look | Art Director |
| 4 | `--force` settle for NSC-046 | Blocks re-dispatching that one task | Game Agent |
| 5 | **Create the Cleanup Agent session** | Nothing else blocks on it, but disk keeps growing | this role |
| 6 | Lower Vault art-direction line | Superseded in part by the canon line that landed; check before re-asking | GER |
| 7 | Environment projection: flat textures vs camera-plane Tilemap | NSC-064 and its PixelLab spend | Art Director + Game Agent |
| 8 | NSC-015 melee split 2 | Shapes that decomposition | GER |
| 9 | Spectral Decoy as the wing reward | Needs a GDD expansion, which is his per-expansion call | GER |
| 10 | Should a relay of his quoted words count as his go for a merge? | Unsettled; the Game Agent flagged it itself | Game Agent |
| 11 | Whitespace lint exclusion for Unity-generated files | Loosens a check in two places | Release + Pipeline Maintainer |
| 12 | NSC-047/NSC-064 elevation sequencing | Changes NSC-064's scope | GER |

Items 6–12 predate tonight and are in `C:\nscrev\reports\for-vincent-20260918.md` with fuller context.

---

## 4a. Open ideas Vincent raised that were never killed and never built

**Found by digesting this session's own transcript, not from memory — which is the point: an author cannot write down what
it has forgotten.** These are not decisions waiting on him; he is not blocked. They are threads that fall through because
nobody owns "ideas". Each is quoted as he said it.

- **A RAG over the documentation.** *"We just want to try to document everything.. Maybe we want to have a RAG on
  documentation?"* (2026-09-17 02:02). A GDD RAG exists; a docs RAG was never discussed again. With the doc set now at ~15
  guides plus a runbook, this is more relevant than when he said it.
- **~~Retiring the gauntlet / putting the main project into gauntlet mode~~ — CLOSED by Vincent, 2026-09-18:**
  *"This one can be forgotten. The gauntlet is no longer needed."* **Do not re-raise it.** Kept here rather than deleted
  because a deleted idea comes back as a fresh idea at the next transcript digest; that is the whole reason this section
  exists.   **Consequence, and one correction to it:** the gauntlet subagent types (`gauntlet-lead`, `gauntlet-observer`, `gauntlet-setup`)
  and the runbook's gauntlet sections may now be dead weight - a Cleanup Agent item, not urgent. **But `reset-task` is not dead
  weight.** Vincent, same conversation: *"We want functionality like reset task, but we dont need the dummy tasks."* The capability
  is wanted, pointed at real tasks rather than gauntlet dummies. **That reopens the naming question for the record-level undo**,
  which was parked partly because `reset-task` held the name. Board `H-20260918-09`. **He then clarified it himself:** *"We should be able to fuck up in our project and reset."*
  So the requirement is **one reset that leaves a real task re-runnable** - revert its commits **and** clear its record. Doing
  only the first is what produced four blocking gates on 2026-09-17/18. Design with Astra after 2026-09-22; no open question for him.
- **A simpler controller for the Game Agent.** *"Maybe we need a less complicated controller for the Game Agent so it has
  less work to do?"* Raised after AssistantControl's controller was parked. It led to discussion and nothing was built;
  the Game Agent still does that work by hand.
- **"no idea where automations are"** (02:14). Never answered. If scheduled automations exist on this machine, nobody has
  located them.

**Don't treat these as a backlog to clear.** Two were deferred deliberately. The value is that a successor knows they exist
and can say "you mentioned X" rather than rediscovering it in three weeks.

## 4b. Queued tools that were never built

**Found by the second transcript-digest pass, not from memory — this role queued them and forgot three.** Each has a written
brief and a board row; only one exists on disk.

| Tool | Intended path | Board row | On disk? |
|---|---|---|---|
| `run_job.py` | `C:\nscrev\job-tools\` | H-20260918-02 | **yes** |
| `ask_astra.py` | `C:\nscrev\astra\` | H-20260917-19 | **no** |
| `new_task.py` | `C:\nscrev\ger-tools\` | H-20260917-25 | **no** |
| `task_run.py` | `C:\nscrev\game-tools\` | H-20260917-27 | **no** |

Briefs: `C:\nscrev\reports\handoffs\ask-astra-tool-brief-20260917.md`, `new-task-tool-brief-20260917.md`,
`task-run-driver-brief-20260917.md`.

**`ask_astra.py` is the one that matters most**, because the escalation ladder's top rung and the deferred undo design both
route through an Astra advice job, and there is no tool for it — it is done by hand each time. Vincent asked for these as tools
specifically because the parameters are error-prone; the Pipeline Maintainer has been busy with defects since.

**Don't assume they were abandoned deliberately.** They were queued, the Maintainer was pulled onto four pipeline gates and a
shoot, and nobody re-raised them. That is the dropped-thread class this section exists to catch.

## 4c. Two things a stranger asked that nothing answered

**`aggregate` on an implementation task does not mean "it has children".** NSC-007 reads `aggregate` in `taskcontrol states` while
having **no** `decomposition_children` and no task naming it as parent - verified. It derives from `execution_scope:
needs_execution_decomposition`: the task is marked for splitting, so it is **not directly dispatchable**, children or not. A successor
reading `aggregate` as "already split" would wait for work that does not exist.

**NSC-007's decomposition succeeded on the fifth attempt** — run `decomp-nsc007-20260918e`, status `review_ready`, after the GER Agent's
revision 8 supplied the missing Play Mode fixtures. **`review_ready` is not applied:** applying it is a main write and needs Vincent's
approval of the exact plan. Until then NSC-007 has no children and cannot be dispatched either way.

**And the authority question, since a stranger could not resolve it:** `C:\nscrev\reports\for-vincent-20260918.md` is the running list
of what needs him, but **board rows H-20260918-07/08/09 were never folded back into it**, so the board is newer where they overlap. If
you keep the list, fold new decisions in or stop maintaining it and use the board alone. Two half-maintained lists are worse than one.

## 5. Settled — do not relitigate

- **The door defect**: blocker 2 units wide in a 3-unit opening, `DoorPrototypeSceneBuilder.cs:1088`,
  `size = (2, 2.5, 0.3)` under a comment reading *"sized to the door's footprint"*. Ten open slots across five doors.
  Fixed by NSC-097.
- **Broken doors** (Vincent): *"A broken door occurs later, dont use it now. YEs an enemy can come through a broken
  door, they broke it."* Out of scope now; when built, the painted hole is a genuine opening and collision follows
  the art.
- **Door art approved** by Vincent after seeing the audit sheet. Recorded at `Docs/Art/Doors/APPROVAL.md`
  (`841fd8133`) rather than in `inventory.json`, because that blob is a pinned conformance surface on NSC-065's
  delivery record and editing it would have invalidated a closed task's evidence.
- **Enemy art is fully wired** — 112 PNGs, all in clips, both controllers attached. An earlier claim that it was
  unused was wrong: the sweep omitted `.anim` and Unity references by GUID, not path.
- **There is no 38% enemy scale pop.** The 176 canvas is PixelLab rotation padding; drawn figures differ by 2.3%.
  The proposed PPU 88 "fix" would have created a real 25% shrink.
- **The wizard importer is the real scale bug**, latent: `ImportWizardSprite` (in
  `Editor/World/DoorPrototypeGlobalSceneBuilder.cs`) hardcodes PPU 180. The 128 px art has **zero referrers** — the
  180 px set is what the clips play — so PPU 180 currently matches reality. Values NSC-096 needs: PPU 64, pivot y per
  variant 0.0469 / 0.0547 / 0.0547 / 0.0625.
- **PixelLab meter figures**: 132 metered against 97 printed on the wizard run, ratio 1.36, derived from readings
  331→463. Supersedes 93, 95/130 and 133. The gap is a per-run measurement, not a rate — a later batch measured
  70 against 70.5.
- **Crew worker lifetime**: the stock profile gives the worker 3600s while a single role may take 3600s, so a repair
  cycle cannot finish. Use `worker-claude-sonnet-long.json` (10800s). Config value, no merge needed.
- **`decomposition_state: concrete` is REQUIRED** by the decomposer, not stale. Opening a task for decomposition
  means setting `execution_scope: needs_execution_decomposition` while `contract_disposition` stays `active` and
  `decomposition_state` stays `concrete`.
- **No override was ever unreachable.** Both launchers forward with `--env`. Three agents claimed otherwise from
  static files; all three were wrong. See section 6 for the one place it *is* path-dependent.

---

## 6. Defects and triggers with dates

- **2026-09-22 18:55 local — Codex quota returns.** Three things happen then:
  1. **The escalation ladder's mixed-provider rung becomes unsafe.** `--env` is injected only on the pooled path, and
     only same-provider pairs pool, so `claude,codex` silently runs at `claude-sonnet-5` while reporting success.
     Memory [[mixed-provider-env-gap-20260922]]. Fix the forwarding or skip that rung.
  2. **The all-Claude banner in `CLAUDE.md` and `nsc-codex-jobs-guide.md` must be removed**, and the temporary memory
     [[codex-quota-out-until-20260922]] deleted.
  3. **The record-level undo design goes to Astra.** It cannot reuse the name `reset-task`; that command already
     exists and reverts an *integrated* task on a gauntlet-replay branch.
- **When `run_job.py`'s review passes** — point `nsc-codex-jobs-guide.md` section 4.3 at it, keeping the manual
  recipe as a fallback.
- **When `propagation_check.py`'s adversarial review passes** — point runbook rule 2 and the merge steps in the
  main-orchestrator and steward guides at it. Board `H-20260917-32`.
- **When `new_task.py` lands** — write the "add a task" procedure into the Viewer Agent's guide.
- **When the Cleanup Agent session exists** — add it to `CLAUDE.md`'s agent list.

---

## 7. Measured economics (all verified, not estimated)

**Tokens.** Desktop account was at **58% of its weekly limit with 3d 21h left**. This session: 658k context, 589k of
it messages. **A message costs the receiver's whole context on the wake-up turn**, so context size is the cost, not
wording — retiring a fat session is worth 5–10× more than shortening prose. Memory
[[agent-message-cost-is-the-wakeup-turn]].

**Crews.** Peak memory **381 MB**, reported by the Game Agent as sampled every 15s across a full run (**no report path or run id recorded - unverifiable as written; re-sample before relying on it**) — the "maybe 4 concurrent from 15 GB free"
ceiling everyone quoted was far too conservative. Memory is not the limit; **one provider account and one Unity
are.** A full crew run with a repair cycle plausibly needs ~6700s.

**The task graph** (measured 2026-09-17, re-measure before quoting): 75 active implementation tasks, 58 remaining,
**15 dispatchable**, 8 of those able to run concurrently, 36 blocked. Only **17 of 95 conformant**. **102 of 119
blocking links point at tasks in `not_delivered`** — the constraint is evidence, not code. Among eligible tasks only
20 of 136 pairs contend, so **86% could run side by side today**.

**Contention, for later**: `Assets/Scenes/DoorPrototype.unity` is claimed by ~31 contracts and
`DoorPrototypeSceneBuilder.cs` by ~27. Harmless while most claimants are blocked; the serialisation point the moment
the enemy chain lands. **That scene is also the only one committed as binary** while every other scene is text and
the project is set to ForceText — converting it and wiring UnityYAMLMerge is the Pipeline Maintainer's "hours, not
days" option and the prerequisite for any deterministic-fileID work.

**PixelLab**: fireball 27 of a 100 cap; death looks 24 of 90; prop pilot 48.8 of 120. Read the balance before and
after with the queue empty and quote the pair.

---

## 8. Documents changed 2026-09-17/18 — do not redo

`CLAUDE.md` (token rules, rewritten to law only); runbook **rules 15–18**; task orchestrator **3a** and **4.4**;
decomposition guide **1a** (NSC-007 triage benchmark) and **1b** (escalation ladder, dated mixed-provider defect);
GER guide (three reshaping traps, criteria-a-crew-can-meet conventions, the relationship-rules convention, the
generation-cap drafting rule); art guide and art bible (settled meter figures); release agent guide; viewer agent
guide (fixed by the Viewer Agent itself); agent directory rows; plus reports
`RECORDING-SCRIPT.md`, `video-script-20260917.md`, `parallelism-analysis-20260917.md`.

Repo commits landed by this role: `e2b80313b` (NSC-078 meter caveat v3), `b7e46c320` (Lower Vault canon v2),
`841fd8133` (door art approval).

---

## 9. This role's failure modes, learned the hard way

1. **Verify before relaying.** Three wrong diagnoses travelled through this role in one night. Each was settled by
   reading the line the tool actually checks, or by inspecting the running thing. [[trust-the-source-not-the-name]]
2. **A relay can manufacture authority.** A decision the Pipeline Maintainer made came back to it through two hops as
   though someone else had made it, with this role's passing agreement attached. **Record decisions on the board when
   they are made.** Board `H-20260918-07`.
3. **Scope a relayed instruction to the exact item.** "We don't want a running crew" applied to one task became a
   general stop and killed the task Vincent wanted filmed.
4. **Quote headroom from the binding constraint.** "40 minutes" came from a role budget when the worker's remaining
   lifetime was 25.
5. **When a second agent repeats an error, fix what they both read.** [[same-mistake-twice-suspect-the-docs]]
6. **Date-only labels follow Vincent's local day; UTC records keep UTC.** This role mis-stamped a whole day and it
   spread to four other sessions. [[date-stamps-verify-clock-and-paths]]
7. **Don't blanket search-and-replace.** It rewrites real filenames. Repair with explicit pairs and check paths on
   disk afterwards.

---

## 10. What I would do next

1. **Check whether the GER Agent has reshaped NSC-007** after the second decomposition rejection. Under the ladder's
   stopping rule that is the correct next step, and the Decomposition Agent is holding.
2. **Watch for NSC-097's crew to finish** and make sure its byte-verbatim requirement is honoured if NSC-098 follows.
3. **Put the gate sitting in front of Vincent as one item**, not five. It is the largest unblock he owns and it has
   been open for two days.
4. **Ask him to create the Cleanup Agent session.** It has been approved and uncreated since 2026-09-17.
5. **Keep the fleet-state file current** (`C:\NSC\nsc-fleet-state.md`) rather than rebuilding this picture from
   messages next time.
6. **Watch the succession round.** Other sessions were told to check their own context and retire past ~250k.
   Each will report a handoff path; Vincent creates nothing — a session can clear itself.

---

## 10a. Outbound claims this role made that proved false

**Nobody else can reconstruct this, and a successor will be asked about it.** Each was corrected to the recipient;
each may still be believed by someone who saw it in passing.

| Claim | To whom | Corrected? |
|---|---|---|
| "The enemy art is unwired, 208 PNGs unused" | Vincent, GER, Art Director, Game Agent | Yes — it is 112 PNGs and fully wired. The sweep omitted `.anim` and Unity resolves by GUID |
| "Enemies pop 38% larger when walking" | Vincent, Game Agent, GER, Art Director | Yes — canvas padding, not figure size. The proposed fix would have created a real 25% shrink |
| "`compose.yaml` has no passthrough, so the model can't reach the container" | Pipeline Maintainer, Decomposition, Vincent | Yes — but it turned out **half right**: true only for the unpooled mixed-provider path, which goes live 2026-09-22 |
| "Three instances of one unreachable-override defect" | Vincent, Pipeline Maintainer | Yes — zero were unreachable; it was three wrong diagnoses |
| "Repeated decomposition rejection means reshape the contract" | GER | Yes — the Decomposition Agent's evidence points at round 2's restructuring step |
| "NSC-007 and NSC-046 both dispatchable; two crews now" | Vincent | Partly — a stale worker record blocked both, and the relay of his stop killed a third task he wanted filmed |

**The pattern in all six: a confident reading of one source, relayed before verification.**

## 10b. Day-one errata — successor, fill this in

Nothing currently measures whether a handoff worked. **Append here as you go on your first day**, then tell the
Documentation Agent what shape the errors took:

**Filled in by the successor, 2026-09-19.** Short, because the file worked.

- **lines that were already false when you read them:** one. Section 2's pointer table said the
  Decomposition Agent had **no** state file; it has a 99 KB one, and `nsc-fleet-state.md` carried
  the same error. Both fixed. Section 4b listing `ask_astra.py` as not on disk is change, not error:
  it exists now.
- **lines you had to re-derive anyway:** every number in section 2 — exactly as that section told me
  to, which is the argument for commands over values. Also "58 GB under `_worktrees`" in section 7,
  which I repeated to Vincent **without** re-measuring. That one is on me, not on the file.
- **lines you never needed:** sections 6 and 7's Codex-return detail, because the reset had not
  arrived; and most of section 3, because each agent's own file answered faster than a summary of it.

**What carried the evening was section 1 — how Vincent writes.** His shorthand table and the rule
that a bare `yes` attaches to the last question were both used inside the first hour, and section
1.4b (reconcile with the agent he told, rather than re-asking him) settled three routing decisions.
**Section 1.0 is the part worth investing in: live state goes stale in hours, and how he
communicates does not.**

## 11. Facts that live nowhere else

- `C:\nscrev\reports\for-vincent-20260918.md` was written on 2026-09-17. Board ids `H-20260918-0x` are likewise
  evening-of-the-17th rows. Both keep their names so references resolve; the board header says so.
- The viewer runs on **port 8828**, colours from `worker.status` (running/starting/ready_pending = blue), and caches
  snapshots for 30 seconds — a run shorter than that can never appear blue.
- `run_unity_tests_clean.ps1` writes failures to stderr while "VALIDATION PASSED" goes to stdout. Reading stdout
  alone shows `total=0` and then nothing.
- The Game Agent's branch `fix/camera-sort-axis-20260918` genuinely carries that name; it is not a date error.
- Docker Claude and the host `claude` CLI run on **cathode26@gmail.com**; these desktop sessions run on the Outlook
  account. **Check with `claude auth status --text` before any host job** — the login has changed mid-day before,
  and about $19 of host jobs once landed on the wrong account.
