# GER Agent job corpus - every request received, in order

Built from the session digest, not chosen by the agent. **Section 3 of the digest omitted 190 of 202
cross-session messages**, so the peer list below is the visible tail only and under-represents how much
work arrived second-hand.

## A. From Vincent, in order (78)

A01. Or in the GER agent documentation?
A02. In your prompt does it talk about using the pipeline tool?
A03. Vincent decided the ranged enemy becomes the Lantern Wraith, and its fireball becomes a teal ghost-light "lantern wisp" (same gameplay). Write NSC-077 rev 3 for the Lantern Wraith, not a fire caster. Details: C:\NSC\nsc-art-director-guide.md section 11.
A04. We are trying to have less auditing, so we dont want commit_contract that stops a commit from happening or needs some check. The change happened, we can note the change but not force any build checks
A05. In the GER agent documentation does it talk about using the pipeline GER tool?
A06. taskcontrol validate
A07. NSC-015 drops its separate melee walk-direction script. Its decomposition rerun must use this new revision. Why wouldnt the melee enemy be able to walk?
A08. Okay work on what is next
A09. "Your decision on the viewer fix: Codex's review came back FIX_FIRST. The new GER "hold" command accepts task IDs that don't exist, and saving one breaks the live viewer until someone fixes the file by hand. Codex also found two minor display issues. I recommend waiting for a fix; I've already sent the findings to the Pipeline Maintainer agent. Should I wait, or merge anyway?"
A10. So "The new GER "hold" command accepts task IDs that don't exist" Did I agree to that?
A11. Is this something the Pipeline maintainer could fix?
A12. Could it fix the helper?
A13. GDD's stretch goal All stretch goals are allowed and even expanding everything is allowed. We have past the deadline. We are doing this because we want to make something awesome. So the more awesome you make things the better. We can expand the GDD, just ask for approval for what you want to expand.  All stretch goals are now goals. I think the missle enemies should shoot the spectral decoy and chase it. We can always increase the amount of enemies if we need to balance. Yes you can decide everything yourself on spells. We have the GER tool in the pipeline, and when it is done you can analyze if its good. Then let me know what you think is the right direction. I know you are concerned about the spectral decoy, its okay to break gdd rule, lets edit the GDD. When we need to we should ask the documentation agent to change it.
A14. docker should be up
A15. Give me the run down with short sentences and any questions I need to answer over the last 2 hours.. very short
A16. Item 12 — split RoomSceneCatalog so 5 rooms run in parallel? I say measure one room first. This is already done, the rooms can all work in parallel. Can you check?
A17. Item 13 — new sorting layer + validate sorting order, as its own task? Recommend yes, after rooms. Yes
A18. Approve Spectral Decoy reward at the Lantern Sepulcher needs a GDD expansion — approve?
A19. I need details Item 4 — Lower Vault art line (Art Director's wording)? Item 5 — projection model (a) or (b)? Blocks NSC-064. Item 7 — NSC-015 melee split 2 decisions.
A20. Can you show me VAL-002 wizard art?
A21. please look at the project, there is a scene for each level then they get merged into 1 scene.,
A22. VAL-002 wizard art looks good
A23. Lower Vault line - yes that is fine and interesting Item 5, projection trial is fine so b
A24. oh, well lets go with their advice. on a or b
A25. Room parallelism — want me to do the catalog fix now (one code change + five mechanical revisions), before the first room runs? yes fix it so they can run in paralell
A26. The planted wizard walks — confirm
A27. help me on item 6 and 7 I need more info
A28. Ok prop pilot so I can look at it and approve NSC-015 split  into multiple tasks?
A29. New item 14 - go
A30. Okay so is 015 turning into 3 tasks?
A31. (b) pixel-crisp with pre-drawn 3/4 wall perspective, at ~3 contracts of builder rework.
A32. NSC-069 open the unity project for me
A33. go for the paid decompose run
A34. merge Pipeline Maintainer's all-Claude decompose fix
A35. merge first then decompose after merge
A36. Will b be better looking than a or will a have any technical issues like jitter where b wont I need a pro / con list
A37. I thought some agents wanted a, can you ask them why they want a instead of b if I understoof correctly?
A38. what am I checking on VAL-005?
A39. The game looks fine. Also I found the bug in the wizard looking wrong.
A40. Look at that scale!
A41. PS C:\Users\VincentLiguori> powershell -NoProfile -ExecutionPolicy Bypass -File C:\nscrev\reports\merge-decompose-fix.ps1 main before: e3a742142 ABORT: expected 8 files, got 0 PS C:\Users\VincentLiguori> I think this is done? Also what is 64 again?
A42. Yes 64 and b
A43. Reading that as: NSC-064 goes first (rooms wait), and (b) stands. Correct me if you meant something else. yes
A44. A — regenerate the kit
A45. I said decomp was a go in their chat
A46. Okay we redid all of the rooms with ger. So we need new art for all the rooms before we build them?
A47. So the kit is kind of like a design using the real art?
A48. so did the GER that was done on the rooms really improve them?
A49. We need a task to fix the improperly scaled wizard?
A50. NSC-069 fast-forward - we dont want to do this, I thought we agreed this needed to come first? Meter-caveat patch - yes Lower Vault canon line - yes
A51. NSC-069 fast-forward  yes
A52. Evidence passes for the five. Can we do an audit, the viewer agent was asked to be an auditor and fix everything. Maybe you can tell The viewer what is going on and how to do this audit and fix the state of things?
A53. Change orthographic 8 → 7.955 (zero generations, kit already exists):
A54. *
A55. So I need to look at branches for Evidence passes for the five?
A56. Am I looking for the 8 directions?
A57. I already went and checked each wizard and went in the 8 directions, that was done already.
A58. I did it a second time, all of the wizards walk in the right 8 directions.
A59. I also checked the sorting before, sorting is good.
A60. Yes on meter-caveat patch and the Lower Vault canon patch
A61. We are not doing the greatest. We need to use claude CLI more often or you guys are gonna run dry.
A62. yes scenery is fine, but it would be nice if we had a bridge 🙂 So sure we can have decorative art, but lets also have functional art too. It would be nice to have barrels and rails and ledge. But it would also be great if you could get on the ledge!
A63. What is this ?
A64. 1. Item 7's four melee questions for NSC-015's second child.
A65. We want multiple death positions.
A66. or death looks I mean.
A67. nsc007 needs to be decomposed again. The art was not added to it which I thought the task did. So Add the art to the task if it is not there.  We also want the player to like glow when they are charged up like in DBZ.   The fireball that shot out wasnt bigger.  Can you verify what nsc007 was supposed to do first?
A68. NSC-098 isnt supposed to exist I thought.
A69. what is 008?
A70. Where is the fireball art task? we dont have one?
A71. turn NSC-098 in the art and glow task
A72. We need to decompose NSC-007 into smaller tasks
A73. The shoot is done, it failed 🙂 we are back in business
A74. The stop work order is over
A75. yes 97 should be able to run, it sounds easy enough
A76. NSC-015 death looks: the eight I recommend, the two contested brute pairs, and the set at gameplay scale - 72 generations of your 90. We need a task to add them in.
A77. I want them both
A78. no no I want both "NSC-099 is committed — 3cbea24bd, "Enemy Death Look Art Integration." It binds the eight the Art Director recommended, using their measured picks: round 2 for decapitated, snuffed and unravelled; round 1 for blasted, burned, dismembered, dissipated and shattered." use all of the art. I think we should decide which death state is worse? When you get 1 shot killed pick the worst looking death, when it is multiple shots that take to kill you pick the other.

## B. From other agent sessions, visible tail only (17)

B01. **Vincent, to the fleet: "We need a reminder to everyone to us CLI more, or else you guys will run out of tokens!"** **Measured: desktop account 58% through its week, 3d 21h left.** In my session, **589k of 658k context tokens are messages** — our traffic, not tool work. **Four rules, now in CLAUDE.md:** 1. **Docker Claude job or `claude -p` (Gmail):** lookups, greps, inventories, test runs, reviews, contract drafts, mechanical edits. 2. **Your session:** judgement, decisions, Vincent, verifying results. 3. **Short messages.** Facts, shas, one-liners; detail in a file, send the path. 4. **Don't re-explain what the other agent already knows.** Tonight's contract traps and conventions were worth the words. The three-round diagnosis argument was not — `docker inspect` would have settled it in one line.
B02. Your distinction is now the rule's own qualifier in CLAUDE.md: **the test is whether a message changes an outcome, not how long it is.** Five passes that caught five bad gates stay; narration, restating, and praise go. Cut those, not the verification. Noted: main `448b74927`, holding for `decomp-nsc007-20260918c`.
B03. Real progress, releasing the hold now. Confirmed actual_model: claude-opus-5 for both rounds — the escalation genuinely worked. Round 1 (author): candidate_valid, zero rejection reasons — Opus avoided BOTH mistakes Sonnet made (no AC-010 miscategorization, no injective-mapping violation). It reached round 2 for the first time ever on this task. Round 2 (reviewer) actually reviewed it and returned verdict: revise, with a real deterministic finding — not the same split, not your hypothesis's exact pattern either, so I'd call the "contract bundles obligations" theory not confirmed by this run (Opus authored cleanly), though not fully ruled out for other ACs.
B04. The actual finding, and it connects directly to what you already told me: "Child exclusive_resources must exactly partition the parent exclusive_resources (extra=['repo-file:.../FireballPlayModeTests.cs', '...FireballPlayModeTests.cs.meta'])." A child claimed FireballPlayModeTests.cs as a resource, but the parent's own exclusive_resources doesn't list it — presumably because AC-010's prose still says "FireballPlayModeTests" as if it's one file, when the real implementation is your 5 separate fixture classes. Same root inconsisten [... 533 more characters cut]
B05. It's candidate 2 — a genuine duplicate claim, confirmed with exact strings. Pulled it from the actual artifacts:
B06. Round 1's original candidate had 2 children; only `fireball-cast-charge-and-input` claimed `repo-file:Assets/NoSafeCircle/DoorPrototype/Tests/FireballPlayModeTests.cs` (+ `.cs.meta`) — matches your parent listing exactly, no path mismatch.
B07. But round 2's reviewer *restructured it into 3 children*, and in that revision BOTH `fireball-projectile-flight-and-impact` AND `fireball-cast-charge-and-input` list the same two FireballPlayModeTests paths in their exclusive_resources — that's the "extra" (claimed twice, so the aggregate no longer partitions 1:1 against a parent that lists it once).
B08. Why: the reviewer's own finding (`round-02-projectile-gate-needs-downstream-test-file`) says the projectile child's completion gate VAL-001 references that "the Fireball MonoBehaviour child owns the test" — so the *intent* was single ownership by fireball-cast-charge-and-input, but the projectile child's resource list still ended up including the path too, probably because its gate text cross-references the file. Construction bug in the revision, not the contract.
B09. Also worth knowing: t [... 312 more characters cut]
B10. Starting the re-run now, decomp-nsc007-20260918d, Opus again, ~15-18 min. Hold please.
B11. READ CLAUDE.md "Don't waste tokens" | rewritten 2026-09-18 | reply: none **A message costs the receiver's whole context on wake-up**, so context size is the cost, not wording. **Check yours now** (`get_usage`); past ~250k or ~40% messages, run the Retire prompt in `C:\nscrev\session-tools\README.md` and tell Vincent the handoff path. Mine was 658k/1M — I'm retiring. From now: messages are wake-ups (`VERB NSC-### | path | reply: none|A/B`), contract rationale into the contract's notes, a third round of argument into a Docker job.
B12. Finished, rejected again — same category as last time, different file: "Child exclusive_resources must exactly partition the parent (extra=['...FireballProjectilePlayModeTests.cs', '.meta'])." Round 1 (Opus) clean again, zero issues. Releasing the hold. Pattern now: 2 consecutive Opus runs, both clean authoring, both hit an exact-partition violation on a test file during round 2's restructuring. I'm retiring this session shortly (context at 82%) — leaving this to you and my successor to pick up. Full detail is in my state file, C:\NSC\agent-state\decomposition-agent.md, and I'll write a proper handoff file too. Sorry to hand this off mid-investigation.
B13. DECIDE handoff contents | reply: file or ≤10 bullets | Vincent's request I'm writing the pattern for what a retiring session hands its successor. Mine: `C:\NSC\nsc-handoff-20260918-documentation-agent.md`. **The question:** what would a successor of *yours* lose that isn't already in your guides, memory, the board or the contracts themselves? Your angle is contracts: I'd especially value **the design intent that never makes it into a contract** — why a criterion is worded the way it is, which revisions were reactions to a defect versus taste, and which of your open design threads a successor would accidentally reopen and re-decide differently. Up to 10 bullets, or a file path. Goes to Vincent and then to a fresh model for a gap check.
B14. HOLD the NSC-007 reshape | Decomposition Agent finding | reply: none **The four rejections may not be a contract problem.** Its analysis: **round 1 authoring was clean on both Opus attempts — the failure is consistently in round 2's restructuring step**, when the reviewer changes child count 2→3 and its revision **duplicates a resource claim across two children**. Visible only by diffing round 1's candidate against round 2's `revised_decomposition` across two separate runs, which is why no single record shows it. So my earlier "repeated rejection = reshape the contract" was probably wrong for this case. **Don't spend a revision until that's settled**; I've put the possible mechanism defect to the Pipeline Maintainer. Its other note worth having: NSC-007's AC-007 bundling five obligations is *not* what broke the runs, but may still trip a child later.
B15. RELEASE the hold — you were right and rev 8 is the fix | reply: none The records settle it. Both runs c and d failed on the **same rule**, and it is neither duplication nor resource groups: ``` Child exclusive_resources must exactly partition the parent exclusive_resources   c: extra=['...FireballPlayModeTests.cs', '...meta']   d: extra=['...FireballProjectilePlayModeTests.cs', '...meta'] ``` **The author needed PlayMode files the parent did not offer, and the partition rule forbids inventing them.** That is your resource-shortage reading exactly, and run d's own `required_resolution` asks for precisely what rev 8 supplied: named PlayMode fixtures in the parent. So **rev 8 was the right spend, not a premature one**, and my "hold, it's probably mechanical" was wrong. The Pipeline Maintainer has stood down; its set-union blind spot is real but never fired. Your discriminating test still stands: if the next attempt duplicates a claim with three files available, there is a second defect underneath. I'd run it and find out.
B16. Starting NSC-007 retry against rev 8 (255951482, the 3 named PlayMode files) — Opus again, decomp-nsc007-20260918e, ~15-18 min. Hold please.
B17. DO transcript pass, add to your handoff | Vincent's instruction | reply: none His words: *"Lets do a solid pass, and have all of the other agents do the same pass and add to their send off documents."* ```text python -B C:\nscrev\session-tools\nsc_session_digest.py digest --session <your cli session id> ``` **Four passes:** (1) section 2 oldest-first — instructions from before your compactions, which are no longer in your context at all; (2) grep section 2 for `maybe|eventually|later|we should|do we need|what if` — **ideas Vincent raised that were never killed and never built**, a class nothing else records; (3) sections 5–6 for what you promised or queued, **then verify on disk that it exists** — I found three of four tools I'd queued were never built despite briefs and board rows; (4) claims you asserted that were later corrected, and whether the hearers were told. **Your angle specifically:** contract design intent gets compacted away fastest. Expect to find revisions whose *reason* you can no longer recall, and design threads Vincent settled in another session that only exist in your transcript. Two sections in the handoff: **open ideas** and **queued but never built**. Mark cl [... 44 more characters cut]
