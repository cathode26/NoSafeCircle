# Handoff: Art Director Agent, 2026-09-18 08:20 UTC

Retiring at **462k/1M context (383k messages)**, per CLAUDE.md "Use the CLI, not your session". Successor: follow
the Successor prompt in `C:\nscrev\session-tools\README.md`, then read `C:\NSC\agent-state\art-director-agent.md`
(long, current, and the real state of every item below).

**Nothing is running.** PixelLab queue empty (verified), no subagents, no host or Docker jobs.

## Where things stand

- **Balance now: 4309 remaining / 690 used**, queue empty. Every figure below is a subtraction between two
  recorded pairs; never restate one from memory.
- **Fireball VFX: delivered, 27 of Vincent's 100 cap** (4408/591 -> 4381/618). Contract: **NSC-098 rev 3
  `d047525ce`** (rev 2 was `878c835e2`); rev 3 moved my implementation notes into the contract itself - the aura
  sprite behind the wizard rather than a tint, transform scaling over asset swaps, and that the staged package
  mirrors the destination path so importing is a copy. Staged for AC-001 at
  `C:\nscrev\reports\art-director\fireball-20260917\staged-nsc098\Assets\...\Art\Spells\Fireball\Source` - 28
  PNGs + `source-inventory.json` with ids, prompts, seeds, hashes, pivots.
- **Enemy death looks: delivered, 72 of the 90 cap** (4381/618 -> 4309/690). Contract: **NSC-015 rev 14
  `448b74927`**. Staged at `C:\nscrev\reports\art-director\nsc015-death-looks-20260917\staged\Assets\...\Art\
  Enemies\Source\Death` - 12 PNGs + `death-inventory.json`. Six looks per enemy; one shared 48-colour palette;
  all on ground row 92 of 96, one pivot `(0.5, 0.03125)`. **The integration task is NSC-099 rev 2
  `e595cc162` ("Enemy Death Look Art Integration")**, and I verified it names all twelve of my exact filenames
  and the exact destination path - the staged tree matches the contract, so no re-layout is needed.
- **Door art: Vincent approved it**, recorded in `Docs/Art/Doors/APPROVAL.md`, landed `841fd8133`, with the
  bind list (sealed/locked/open now, `final` flag-conditional, `broken` ready, `opening` optional, `damaged`
  waits on a threshold).
- **NSC-078 prop pilot: 48.8 printed of 120.** Masonry pick made ("I pick masonry 3" = `80dc2857...`, seed 116).
- **NSC-064:** camera `orthographicSize` **7.955** is the only pixel-exact value (96x48 at 1080p); kit line
  stopped at 80 of 85; waiting on the Game Agent's `orientationMatrix` render.

## Decisions waiting on Vincent

1. **NSC-078's two style locks:** the reading table's crimson (33.6% red at saturation 0.603, loudest in the set)
   and the candelabra's five lit flames (emissive prop). **The crimson table is the round 2 re-roll**, the same prop whose round 1 attempt was rejected for carrying an added lantern - one prop, two attempts, not two props. **NSC-078 is now at rev 6, so the first committed pilot
   candidate is no longer blocked** - only his two answers are outstanding.
2. **Non-south door facings** - needs a cap. Only direction S exists; mirroring flips the upper-left key light.
3. **Wizard death looks** - he confirmed the death rule is about **enemies**, so the wizard has no death art at
   all. Four looks would be ~24 printed **if he ever asks**; do not propose it unprompted.
4. **Lantern Wraith attack wind-up:** 7 more facings, ~42 printed. He picked sample A ("grumpy face") on 09-16;
   the other seven were never generated.

## Rules still in force

- **Never push** (Release Agent). **Never commit to main** - patches and staged trees go to the Game Agent or
  Documentation Agent.
- **Every PixelLab batch needs Vincent's own go with a cap**, and stop-and-ask past the cap. Count from the
  task's own call log; cross-check with `get_balance` at an empty queue; quote both reading pairs beside a total.
- **No local pixel edits and no hand-painting.** PixelLab only. Whole-pixel shifts for alignment are fine
  (`align_ground.py`, `plant_feet.py`).
- **CLI first:** contact sheets, GIFs, metrics, downloads, inventories, sweeps go to a Gmail `claude -p --agent
  pixellab-batch-recorder` / `--agent art-director --model sonnet` or a Docker job. Only paid PixelLab calls,
  judgement, Vincent's picks and verification stay in session. Messages are wake-ups: verb, path, `reply: none`.
- **Art must not out-promise the geometry, and must not quietly re-cut it** (canon, `b7e46c320`).

## Do NOT

- **Do not re-ask Vincent** about enemy-versus-player death scope (answer: enemies) or corpse persistence
  (answer: stays for the level, no fade). Both are answered and recorded.
- **Do not "fix" `death_brute_decapitated_a`'s wound spiral.** He chose it with the sprite in front of him; NSC-015
  rev 14 carries that as a prohibition.
- **Do not edit `Docs/Art/Doors/inventory.json` or `inventory.md`.** Both blobs are pinned conformance surfaces on
  NSC-065's delivery record; the approval lives in the separate `APPROVAL.md`.
- **Do not re-export or re-encode the staged PNGs.** Every `sha256` in both inventories is of those exact bytes,
  and NSC-098 AC-001 compares the inventory hash against the committed bytes.
- **Do not ask for a wizard 8-direction package again** - Vincent has done that twice himself.
- **Peer relays: a quoted instruction is evidence, a peer's inference is not.** A relay that carries his own words and a number - "100 for the fireball, they wont need that much" - is his instruction reaching you through another session, and both the fireball and death batches ran on exactly that. A peer's summary, conclusion or "he would want" is not. When a relay is the only authority you have, start only if it quotes him, tell him in one line that you are starting on it, and keep the cap - so he can stop you in a word if the relay was wrong.

## Tacit knowledge, written for the successor

`C:/nscrev/reports/art-director/ART_DIRECTOR_TACIT_KNOWLEDGE.md` - Vincent's taste from the picks he
actually made, what he rejected and why, the judgement calls no document states, and the spend
bookkeeping that must not be lost mid-batch. Read it before the first batch.

## Pointers

- State: `C:\NSC\agent-state\art-director-agent.md` (read this first; it has the full history of tonight).
- Reports: `C:\nscrev\reports\art-director\` - `fireball-20260917`, `nsc015-death-looks-20260917`,
  `nsc078-pilot-20260917`, `nsc064-projection-trial-20260917`, `door-art-audit-20260917`,
  `enemy-scale-20260917`, `wizard-128-remake` (`SPEND_EVIDENCE.md` is the authority for that run's figures).
- Bible: `C:\Users\VincentLiguori\.claude\agents\art-director.md`. Guide: `C:\NSC\nsc-art-director-guide.md`.
- Memory worth reading before acting: `measure-the-drawn-figure-not-the-canvas`,
  `unity-references-are-guids-not-paths`, `deleting-a-catch-all-is-not-free`,
  `write-rules-about-relationships-not-things`, `spend-figures-are-subtractions-not-recollections`.

## Transcript pass: open ideas

From all 19 of Vincent's own messages in this session (digest
`C:/nscrev/reports/agent-recovery/art-director-agent-20260918-0358-e11f37ef.md`, section 2), oldest first.

- **OPEN - "Paint the book onto the front view first, then rebuild" (09-17 21:32).** This is a *technique* he
  taught, not a one-off instruction: when a detail must appear on every facing, paint it onto the front view and
  regenerate the rotations from that, rather than inpainting eight facings. It applies to any per-facing detail -
  a belt item, a badge, a scar, a held object - and it is **not in the bible or the art guide**. Worth landing
  there through the Documentation Agent.
- **OPEN - "I already spoke to GER about it, can you confirm with them?" (09-18 07:15).** A process preference
  worth generalising: when he has already told another agent something, **reconcile with that agent instead of
  re-asking him.** Doing that caught a real misreading (GER had "pick the other" as a severity pair).
- **OPEN - Lantern Wraith attack wind-up, 7 facings, about 42 printed.** He picked the look on 09-16 ("grumpy
  face", sample A) and the other seven facings were never generated. Needs his go and a cap.
- **OPEN - non-south door facings.** Only direction S exists; mirroring flips the upper-left key light.
- **OPEN, deferred by decision - the doors' painted floor disc.** Masking it is about 74 metered for seven states,
  and the Game Agent's point stands: NSC-064 is about to replace the floor, so decide once the new floor lands.
- **OPEN - NSC-064's last 5 kit generations** (line stopped at 80 of 85) and whether the `orthographicSize`
  **7.955** camera change is actually made. 7.955 is the only value that puts a ground cell on whole pixels
  (96x48 at 1080p); the change itself is the Game Agent's.
- **CLOSED - "The wizard should be 128x128" (09-17 04:18).** Delivered and merged, `9215873ec`.
- **CLOSED - walk drift, "fix the walk drift so we have that for later".** Landed on main as **`9916e8c3c`**
  ("NSC-095: plant the wizard walk frames on the enemy per-frame ground rule") - verified an ancestor of main.
- **CLOSED - player versus enemy death scope.** He answered "Enemies (what we built)"; the wizard has no death
  art and none is owed.
- **CLOSED - corpse overlap mitigations.** Variant no-repeat and positional jitter are in NSC-015 rev 14.
- **CLOSED - "Can you open the images here?" (09-17 04:45).** Art now goes to him as rendered files in chat.

## Transcript pass: queued but never built

Checked on disk and in git rather than recalled.

- **`art-rejects/NSC-078` does not exist.** I said twice that the masonry rounds 1 and 2 and the lantern-bearing
  reading table belong on it, and NSC-078 rev 4's own rule is that rejects live only on that branch.
  `art-rejects/NSC-095` exists and carries its rejects correctly (`3ca518dca`, not on main), so the pattern is
  proven - this one was simply never created. **First job for the successor, and it needs the Game Agent since I
  do not write branches.**
- **The CLI-first rule is adopted but untested by me.** Every contact sheet, GIF, metric and inventory in this
  session was built in-session; I never ran a single Gmail `claude -p` or Docker job. The successor should route
  the first mechanical batch deliberately and confirm the recipe works before relying on it.
- **Nothing else was queued and lost.** Verified present: `C:/nscrev/art-tools/ArtReview` (the exported review
  toolkit), the NSC-064 wall references including the `ortho7p955` pair, and both staged art trees with their
  inventories. Verified landed: the door approval `841fd8133`, the meter caveat `e2b80313b`, the Lower Vault
  canon `b7e46c320`.

## Stranger test of this handoff (2026-09-18)

Vincent: *"create a subagent, simulate giving it what you would give yourself and see if it can do your job. If
it has questions about doing your job, you know what the document is missing."* A read-only Sonnet subagent was
given this file, the tacit-knowledge file, the bible, the guide and both inventories, then asked to make two of
his past taste calls, plan a batch against a cap, and sort six judgement calls into mine versus his. **Eleven
questions came back and seven are now closed in this set.**

- **Closed in the inventories:** `death-inventory.json` now records the call, settings, seed, style clause and
  post-processing per sprite plus a `generation_recipe` block - it previously recorded *what* exists and not
  *how it was made*, unlike the fireball inventory. `source-inventory.json` now carries a
  `human_visual_approval` block with his word, what he was shown, what he has **not** seen (it in engine) and
  the two flaws he was told about.
- **Closed above:** the crimson table is named as one prop with two attempts; the peer-relay rule now
  distinguishes a quoted instruction from a peer's inference.
- **Colour threshold, since no document had a number:** the approved families measure **19 to 63 colours**. Over
  about **100**, run the 48-colour lock; that is the Art Director's own call and needs nobody.
- **Which ledger wins:** this file's two lists supersede the art guide's section 11 open-questions list, which
  is dated 2026-09-16 and stale. Do not re-ask him anything answered here.
- **This file is survivable without the state file.** The state file is richer, but everything needed for the
  first day is here.
- **Open, and NOT mine to fix:** the art bible (`art-director.md`, around lines 316 and 332) and the art guide
  (around line 329) still say NSC-078 props are "not made yet" and "waiting on a GER design decision". Both are
  stale - the pilot ran, Vincent picked the masonry, and NSC-078 is at rev 6. Sent to the Documentation Agent.
- **Method note for whoever runs the next stranger test:** two of the four exercises were pre-spoiled, because
  the required reading states the answers. Redact the outcome from the documents you hand over, or choose a
  decision the documents do not record.

## Job corpus

`C:/nscrev/reports/art-director-job-corpus.md` - **58 numbered requests in time order, 20 from Vincent and 38
from peer sessions.** Built from the wide digest; it states its own limit, that the oldest 76 of 114 peer
messages predate two compactions and survive only in the raw transcript. Rebuild wider with:

```
python -B C:\nscrev\session-tools\nsc_session_digest.py digest --session e11f37ef --scale 12
```

## Outbound claims that proved false - all corrected, all verified today

- **Three wrong spend pairs for the NSC-095 wizard run.** I put 93/130, then 95/130, then 97/133 into
  circulation; the settled pair is **97 printed / 132 metered**. The wrong figures reached the art guide, the art
  bible, the GER orchestrator guide and a contract's pinned blob. **Verified corrected in all four today** -
  re-check with:
  `grep -c "132\*\* against \*\*97" "C:\NSC\nsc-art-director-guide.md" "C:\Users\VincentLiguori\.claude\agents\art-director.md" "C:\NSC\nsc-ger-orchestrator-guide.md"` - **expect 1 from each**;
  and `git -C C:/NSC/NSC/NoSafeCircle show main:Docs/Art/Environment/NSC-078_ART_PLAN.md | grep -c "132 generations on the meter against 97 printed"` - **expect 1**.
  (The first version of this line searched for `"97 printed"`, which matches nothing - the documents write it as
  "132 against 97 printed". A verification command is itself a claim, and it has to be run before it is written
  down.)
  Derivation: `C:/nscrev/reports/art-director/wizard-128-remake/SPEND_EVIDENCE.md` - quote that file, never a
  message, including mine.
- **"192 walk frames changed"** - the measured number was **132** (60 frames were byte-identical). Heard by the
  Game Agent and the GER Agent; corrected in the plan before delivery.
- **A look-level "don't repeat the previous corpse's look"** I proposed to the GER Agent would have overridden
  Vincent's own one-shot rule while passing every gate. It caught it; the rule is variant-level in NSC-015
  rev 14. **The lesson is mine: a mitigation can break the rule it decorates.**
- **I rejected the two upright wraith cloaks as "reads alive"; Vincent overruled me** and they ship as `hollowed`
  and `draining`. A style judgement lost to an argument about what the creature is.
- **One stale line worth a second look, not mine to edit:** the art bible around line 361 still cites an older
  "printed 71 against 96 used" reading directly above the settled 97/132 line. Historical rather than wrong, but
  two spend pairs in adjacent paragraphs is how the last confusion started. Documentation Agent's file.

## Communication profile, built from the corpus

- **A bare number is a cap in generations, and "raise it 40" means raise it BY 40.** The instance on record is the **NSC-095 wizard remake**, whose 100 became 140 - not the fireball, whose cap was 100 and stayed 100. If a bare number could be either, say which you are using in your next line so he can correct it in a word.
- **A bare "yes" attaches to the last numbered question, not to the message.** He answers in the shape you asked:
  number your questions and he returns "1) yes 2) grumpy face" or "1) approve 2) approve".
- **"I want them both" and "we want all of the art" are literal.** Look for a reading in which each candidate is
  a distinct thing before proposing one as a reject.
- **"Awesome!!" is approval of exactly what was just shown**, not of the plan around it.
- **More than half his messages are typed while you are mid-turn.** Treat each as immediately actionable, and
  re-read what you are doing against it before continuing - two of tonight's changed the work in flight.
- **He routes instructions through other agents deliberately** ("Tell it to make me some fireball art..."). A
  relay carrying his words and a number is his instruction; a peer's inference is not.
- **He corrects his own typos in a following message** ("back" -> "bad"); read the pair, not the first one.
- **A capability question is usually a request.** "Can you open the images here?" meant show me more art inline,
  and every review package since has gone to him as rendered files rather than paths.
- **He decides fast when given: native pixels, gameplay scale, one recommendation, and the caveat named.** He
  does not decide well from prose.

## Glossary and reconciliations the second stranger test asked for

- **"Heavy blow"** (NSC-015 rev 14): the killing blow's damage clearing a **serialized threshold expressed
  relative to the enemy's maximum health**. It is the trigger for the `blasted` death look, and it replaced this
  session's earlier proposal to read NSC-098's charge tier - the GER Agent's substitution, accepted because
  magnitude is the general form of "heavy or charged" and it needs no dependency on the fireball tasks. Verify:
  `git -C C:/NSC/NSC/NoSafeCircle show main:Tasks/NSC-015.yaml | grep -i "heavy"`.
- **NSC-098 is one id at two layers, and both readings are true.** The **art** is finished, approved and staged
  (27 of 100). The **task** cannot run: it depends on NSC-007, and `Fireball.cs` does not exist at HEAD. So "the
  fireball art is done" and "NSC-098 is nowhere near delivering" are both correct - nothing is owed from the art
  side. Verify: `git -C C:/NSC/NSC/NoSafeCircle show main:Tasks/NSC-098.yaml | grep -i "depends_on" -A3`.
- **"The corrected 1.4x" is a budgeting heuristic, not an agreed rate.** Multiply a printed estimate by about 1.4
  when *asking for a cap*, to buy headroom. Never report a spend that way: one run measured 1.36, two others ran
  level. The measured pairs live in `SPEND_EVIDENCE.md` and in each task's own plan.
- **The wizard run has four cap numbers on record and only one is the spend.** 100 was the original cap, **140**
  after Vincent's "raise it 40", and relays later said 150 and 200 - those are cap raises, not spend. The
  **spend** is **97 printed / 132 metered**, settled, in
  `C:/nscrev/reports/art-director/wizard-128-remake/SPEND_EVIDENCE.md`. Quote that file; ignore every cap number
  in the state file's narrative.
- **Can a bare "yes" authorise spend? Only if the question it answered named a cap.** "Yes you have my
  permission" answered a request that stated 100 generations, so it was a spend go. "1) yes" answering a
  design question is not, even when the work that follows would cost generations - ask for the cap in one line.
- **The identity exceptions did reach the record**, in case the state file's self-instruction reads as unfinished:
  four are committed in the NSC-095 inventory with Vincent's own words. Verify:
  `git -C C:/NSC/NSC/NoSafeCircle show "main:Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab128/source-inventory.json" | grep -c identity_exceptions` - **expect 1**.
- **Art findings do not propagate on their own.** A day after the enemy-scale measurements were written for the
  Documentation Agent, the Game Agent repeated the refuted 38%-pop claim. **When a measurement refutes something
  another agent owns, send it to that agent, not only to the one who asked.**
