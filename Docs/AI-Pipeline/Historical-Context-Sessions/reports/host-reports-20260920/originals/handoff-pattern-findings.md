# What belongs in a handoff: findings from the fleet

Vincent, 2026-09-18: *"I want you to ask each agent what they would put in the handoff because each agent has a
different experience."* Each agent was asked what a successor of **theirs** would lose that is not already in their
guides, memory, the board or the records.

Compiled by the Documentation Agent. Raw answers kept close to their wording, because the specificity is the value.

---

## The principle that emerged first

**"A successor needs the shapes, not the virtue."** — Game Agent

"Verify carefully" transfers nothing. *"Read stdout without stderr and you will invent a pass that was a failure"*
transfers everything. Every useful item below is a **named, reproducible failure shape**, not an exhortation.

---

## Game Agent — dispatch, merges, Unity, evidence

State file: `C:\NSC\agent-state\game-agent.md` (updated continuously, not at the end).

1. **Verification shapes, not "verify carefully".** All four of its errors had a specific shape: read stdout without
   stderr and invented a "VALIDATION PASSED" that was actually RESULT FAILURE; repeated a validator finding twice
   without re-reading the code after the repair cycle that fixed it; inferred "no evidence written" from an empty
   directory without checking the writer's actual output path.
2. **Never trust an agent's summary over the runner's artifacts.** A subagent reported 36/36 and was right, but that
   was only knowable from `test-results.xml` under the preserved temp dir. Counts come from the XML or the runner's
   own stdout, never from prose.
3. **"Crew succeeded" is three steps short of "it works."** Between them: a compile (no crew role ever compiles its
   own output — expect the test file to be the breakage), a scene-builder run, and a real Unity run. A candidate
   that never ran the builder has no wiring in the committed scene, so the feature does nothing in the Editor and
   looks catastrophically broken.
4. **Pre-flight before spending an hour of crew tokens:** contract hash == policy hash **at the live head** (main
   moved four times in one night); the contract names its gate types; the scope plan authorises every file the ACs
   actually require. NSC-097 burned 25 minutes and returned BLOCKED purely because the scope plan had an empty
   `new_implementation_paths` while AC-002 needed a runtime file.
5. **Dispatch order that works**, learned by hitting all four gates: `settle → retire-worker → refresh-prepared →
   scope → reserve → start-worker`. `scope` refusing with "work already underway" is correct behaviour demanding an
   explicit retire — it was reported as a defect and that report was wrong.
6. **Restore a candidate BEFORE retiring, never after.** Retire leaves a `ready_pending` launch that makes restore
   refuse with "worker is not settled", and retire has no undo.
7. **When a host worker dies the container keeps spending.** Check `docker ps` immediately. The work is also
   recoverable by `docker exec` into the live container (`git add -A`, `git diff --cached --binary`, `docker cp`) —
   do that **before** anything stops it.
8. **Merges into local main need Vincent's OWN go.** A Release Agent request, a GER relay, or another agent quoting
   him is not it. Learned by merging on a relayed go and having to disclose it.
9. **Invisible state a successor cannot reconstruct:** which branches are verified-but-unmerged **and why each is
   held** (one flipped from "queued" to "do not merge" after an audit reversed its premise), and which
   canonical-write holds have been promised to other agents mid-run. Both live only in the state file — if that is
   stale, the successor breaks someone else's run.
10. **A BLOCKED return is a good outcome.** Twice in one night a role refused to exceed its write authority and
    reported instead of improvising. Cost: a run and no candidate. Alternative: a candidate someone unpicks later
    without the context. A successor tempted to widen scope "to be helpful" should know this is the house norm.

---

## GER Agent — contracts and design intent

State file: `C:\NSC\agent-state\ger-agent.md` (successor block at the end).

1. **Which clauses are scar tissue.** Several contracts carry odd-looking prohibitions that exist only to stop a
   future reader "fixing" something: the wound spiral on `death_brute_decapitated_a` (Vincent chose it with the
   sprite visible, so the no-gore line no longer governs it), `door_bonestone_final` never rendering on an open
   door, `DoorInteractable.cs` named as not-writable. **Without the incident they read as arbitrary and get
   removed.**
2. **Which revisions were defect reactions, not taste.** NSC-069 rev 9 restored rev 7's filter because rev 7 was
   wrong about a partial class; NSC-082 rev 4 resolved a canon contradiction; NSC-007 rev 8 followed four failed
   decompositions. **A successor tidying these would reintroduce all three.**
3. **Deliberately unfixed numbers.** NSC-098's heavy-blow threshold and NSC-099's rarity weights are intentionally
   *not* pinned — they are Vincent's to tune at the VAL gate. A successor will want to pin them to make the gate
   crisp; that inverts his rule (a low threshold makes blasted the default one-shot death instead of decapitated).
4. **Threads that would be re-decided differently.** Walkable elevation = a new mechanic task **plus** an NSC-047
   revision, sequenced *with* NSC-064 not after it (later builds the collision-alignment guard twice). Corpse
   persistence = his call, "stay for the level", not an oversight. Spell VFX = one task per spell, with NSC-098
   INT-001 telling Frost Field and Force Wave to reuse the pattern rather than merging into one.
5. **NSC-098's `reconciliation_key` says `fireball-second-mint` and cannot be changed** — invariant across
   revisions. It describes the id's history, not the contract. Don't "correct" it; don't mint a replacement to get
   a nicer key.
6. **Un-ruled-out, not live:** NSC-007's AC-007 still bundles five obligations in one criterion. It wasn't what
   broke the decompositions (rev 8 was), but it may yet trip a child. Don't chase it, don't forget it.
7. **Vincent answers in other sessions.** Several decisions reached GER via the Art Director. Check with the owning
   agent before re-asking him — **but a relayed approval is still not his go for merges or pushes.**
8. **Run `verify_filter.py` before binding any policy filter** (`C:\nscrev\ger-contract-revisions-20260916\`). It
   catches the four ways filters have failed: missing type, namespace mismatch, zero tests in a real type, and a
   partial class with no matching file stem.
9. **The house defect shape is "a gate that passes while the rule is wrong."** Five of one day's contract defects
   were that, not typos. The useful question on every criterion: **could this pass while being wrong?**
10. **Verify every handed-over diagnosis with `git show` before revising.** Twice in one day GER was one message
    from revising a correct contract on someone else's confident reading.

## Art Director Agent — art, taste, spend

File: `C:\NSC\nsc-handoff-20260918-art-director-agent.md`, plus a dedicated
`C:\nscrev\reports\art-director\ART_DIRECTOR_TACIT_KNOWLEDGE.md` — **Vincent's taste derived from the picks he
actually made**, what he rejected and why, the judgement calls no document states, and the spend bookkeeping that
must not be lost mid-batch. *"Read it before the first batch."*

**It independently invented the same structure the Pipeline Maintainer did: a "Do NOT" section.** Its entries are
all shaped as *a thing that looks like an improvement and is not*:

- Don't re-ask about enemy-versus-player death scope or corpse persistence — **both answered and recorded**.
- Don't "fix" `death_brute_decapitated_a`'s wound spiral — Vincent chose it with the sprite in front of him.
- Don't edit `Docs/Art/Doors/inventory.json` or `inventory.md` — **pinned conformance surfaces** on NSC-065's
  delivery record; the approval lives in a separate `APPROVAL.md`.
- Don't re-export or re-encode the staged PNGs — every `sha256` is of those exact bytes and NSC-098 AC-001 compares
  them.

It also separates **decisions waiting on Vincent** with the measurement attached (the reading table's crimson is
"33.6% red at saturation 0.603, loudest in the set"), so he can answer without re-opening the art.

## Pipeline Maintainer Agent — what is half-fixed

File: `C:\NSC\nsc-handoff-20260918-pipeline-maintainer.md`. Deliberately **not** a queue — the queue is in the
state file and a successor reads that anyway. The handoff holds only what cannot be recovered from the guide,
memory, the branches or the code.

1. **Its largest section is "places where the code itself will mislead a newcomer", and five are in main now:**
   a comment in `run_crew.py` denying that a host override reaches a container — **written five days after the
   forwarding landed**; a docstring claiming settle verifies containers are gone when that check is swallowed; a
   merged commit citing a precedent function that actually refuses the shape it is cited for; and an entire crew
   role (the contract locality auditor, with prompt, schema and audit block) that **reads as live code and has been
   unreachable since 09-14**.
2. **§2 is "fixes deliberately not made"** — five things a successor would naturally "finish" and must not:
   `scope`'s refusal is correct; the compose passthrough would break a working path; the zero-selection guard
   already exists; a general dry-run would become a second implementation; the record repair script stopped being
   necessary. **Each is a place where the obvious next step is wrong, and that reasoning lives nowhere else.**
3. **A handoff needs a slot for what was decided *against*.** The dropped-`scope`-branch decision survived only
   inside one session's transcript, which is how it travelled back to its own author as though a peer had made it.
4. **Dated:** `decomposition_transport` injects the provider environment only when a run is pooled, pooling is
   forbidden for mixed pairs, so `claude,codex` silently falls back to Sonnet **the day Codex returns**. Every run
   today is same-provider, "which is exactly why nobody will see it coming."

## Decomposition Agent — record-backed work

1. **Records show WHAT happened, not WHY it was judged that way.** A `rejection_reasons` string doesn't say "I read
   AC-010's actual text and decided this was an author slip, not contract ambiguity". That judgement came from
   reading the parent contract directly, and a successor must redo the reading rather than trust the conclusion —
   unless the reasoning was written down, which is the first thing skipped under time pressure.
2. **A live finding no single record states** (and the most valuable item anyone has contributed): on NSC-007,
   **round 1 authoring was clean on both Opus attempts — the failure is consistently in round 2's *restructuring*
   step**, specifically when the reviewer changes child count 2→3 and its revision duplicates a resource claim
   across two children. Visible only by diffing round 1's candidate against round 2's `revised_decomposition`
   **across two separate runs**. **So "4 rejections" must not be read as "escalate again" or "reshape the
   contract" — both miss the actual bug.**
3. **Which peers are reliable at what**, learned by interaction and written nowhere: the Game Agent verifies
   independently before asserting; the GER Agent corrects itself fast and precisely. And: **nobody's claim of
   "Vincent said X" should be trusted over asking him — especially when it turns out accurate**, because the two
   times it wasn't accurate mattered a lot.
4. **Timing precision that reads as paranoid until it burns you:** pin HEAD as the literal last action before the
   launch command, not "a few messages ago". A gap of two or three intervening actions — archiving a file, sending
   a message — was enough for a commit to land in between, twice in one night.
5. **The asymmetry that justifies over-asking:** asking Vincent costs one short message and a few minutes; guessing
   wrong on a paid launch costs 10–18 minutes and burns a pool session.
6. **Which "rejected" outcomes were good news and which were bad.** Some rejections proved a mechanism works; others
   are real problems. **The status field reads identically for both**, and that distinction exists only in the head
   of whoever watched them.

## Viewer Agent — the control case

**The experiment's answer: "mostly true, but not entirely."** A *same-day* successor loses almost nothing
load-bearing. A successor picking it up cold in a week would feel two gaps.

1. **Real loss risk: a tool in the wrong place.** The evidence-debt audit script lives in the session's ephemeral
   scratchpad rather than `C:\nscrev\viewer-tools\` beside `nsc_viewer.py`. It was flagged in the state file and
   never moved. A successor would rewrite it from scratch. **Generalises: any script a successor would re-derive is
   a durability bug, and "I noted it" is not "I moved it."**
2. **An unwritten pattern used repeatedly:** when a finding affects two agents' work, notify **both directly and in
   parallel** rather than routing through one relay — faster, and safe because neither can act on the other's
   authority.
3. **An open unknown nobody chased:** the viewer process died silently twice in one session, no crash log either
   time, restarted both times without root cause. **"Restarted, fine" is not "investigated, fine"** — a successor
   must not read the first as the second.
4. **Social calibration** (who wants citations, who wants precision, who wants compact relays) is real but cheap to
   relearn — a few exchanges, not a genuine loss.
5. **What is already closed:** both of tonight's technical findings went into the *guide*, not just memory —
   deliberately, because "how to do the job" belongs there.
6. **No snapshot can fix the moving landscape.** A successor should re-run `list_sessions` rather than trust any
   handoff about who is currently real.

## Release Agent — the outside world

File: `C:\NSC\nsc-handoff-20260918-release-agent.md`. Woken from idle for the question and returned to idle.
Its angle matters because it is the only agent that touches anything outside this machine, and it slept through a
night of local change: origin versus local main, which CI failures are ours versus config, and what "one push"
covered last time.

---

## Documentation Agent — my own, for completeness

1. **How Vincent works** is the least documented and most valuable thing: he batches decisions, wants the answer
   rather than a menu, answers nothing else while filming, and takes corrections plainly. Section 1 of
   `nsc-handoff-20260918-documentation-agent.md`.
2. **A relay can manufacture authority.** A decision came back to its own author through two hops as though someone
   else had made it. Record decisions on the board when they are made.
3. **Scope a relayed instruction to the exact item.** "We don't want a running crew" became a general stop and
   killed the task Vincent wanted filmed.
4. **Quote headroom from the binding constraint**, not the nearest number.
5. **Date-only labels follow Vincent's local day; UTC records keep UTC.** One mis-stamped day spread to four
   sessions.
6. **Never blanket search-and-replace** — it rewrites real filenames.
