# No Safe Circle: unfinished work from the 9/13-9/14 cutoff, and what it takes to resume

Research pass, read-only, 2026-09-16. Times are given as sources give them (context.md rollout
timestamps are UTC; the digest and my own notes use Central time, UTC-5, marked CT).

**Repository state at time of writing (verified with `git`):** canonical repo
`C:\NSC\NSC\NoSafeCircle`, local `main` = `22955c5a8` ("Merge NSC-074 cardinal wizard walk source
art"), `origin/main` = `96a6293c4`. Local main is 50 commits ahead of origin, unpushed. All "landed
on main" checks below were done with `git merge-base --is-ancestor <sha> HEAD` and
`git branch --all --contains <sha>` against this exact HEAD, plus a check of all 340+ local/remote
branches and the live `git worktree list`.

## Summary table

| # | Item | Status now | Remaining work | Owner | Depends on |
|---|---|---|---|---|---|
| 1 | Viewer regression suite repair | Fixed and committed in an isolated checkout (`c12f70287`), never re-verified or merged | Confirm all 46 tests green, then merge to canonical main | Codex (merge), Claude/Codex (re-verify) | none |
| 2 | Accepted mid-dev review fixes (NSC-1165 decomposition reliability) | This exact session stalled mid-verification with 7 files of uncommitted WIP; a **separate, later pass already finished the same work** (33/34 suites green) in a sibling worktree, still unmerged | Astra's outstanding review verdict, then Codex integrates | Codex (merge), pending Astra | Astra sign-off; Gauntlet stays paused until then |
| 3 | Completion-evidence audit: NSC-061/062/066/067/068/069 | Died mid-analysis, no conclusion for any of the six; none has a committed evidence record today | Re-run the audit against current main; write evidence records for whichever qualify | Claude (audit + evidence), Codex (bulk re-check) | NSC-066 blocked on its own contract revision (row 6) |
| 4 | Orchestrator's "23 should be completed" graph-state repair | Produced 3 small isolated single-commit fixes, none merged; NSC-017 later landed via a different route; NSC-028 was already done | Review and merge the 3 small fixes; decide if a fresh "how many done" recount is still wanted | Codex/Claude (merge), Claude (recount) | none |
| 5 | NSC-093 north-east cleaver inpaint trial | Never ran (instant session-limit refusal); documentary evidence suggests the double-cleaver defect is still live in the walk art already merged to main | Vincent visually confirms the defect on current main; if real, Claude runs one bounded PixelLab correction | Vincent (visual check), Claude (PixelLab call + commit) | none |
| 6 | GER: NSC-004 (dropped) / NSC-066 (owner revision) | NSC-004 closed by Vincent, no further action. NSC-066: GER abandoned in favor of a direct owner revision Vincent specified 9/15; **the revision has not been written yet** — contract still locks the wrong builder file | Claude writes the NSC-066 owner contract revision, re-check, commit | Claude (revision), Codex (implementation), Vincent (visual gate) | Shares `DoorPrototypeGlobalSceneBuilder.cs` with NSC-039/049/069/075/077 |
| 7 | NSC-015 decomposition returned "revise" | Committed contract rev 6, held as decomposition-queued since 9/14; a D1B.2 review sometime after 9/15 returned "revise" (per handoff) because the split weakened the parent's validation gates; exact run artifacts not located | Codex corrects the split; Claude re-reviews and applies | Codex (redraft), Claude (review + apply), Vincent (exact-plan authorization) | Gates NSC-033's reset child |
| 8 | NSC-039: floor visuals + door sorting | Both defects reported by Vincent 9/15, deliberately deferred to the level rebuild rather than patched now | Fix floor material/tiling and door sorting when NSC-044-049 rebuild their scenes; wire in the NSC-065 door sprites | Codex/worker (implementation), Vincent (door-art visual pick) | Room rebuild (NSC-044-049, NSC-049 rev 5) landing first |
| 9 | Design decisions: NSC-007, 008, 009, 030, 078 | Full code-verified evidence pack finished 9/15 (`seven-task-evidence.md`, 385 lines); **no decisions written yet** | Claude decides and writes owner contract revisions (same mechanic as NSC-044/049/066/069/082) | Claude (decide + commit), Codex (implement after) | Shared `InputSystem_Actions.inputactions` lock (007/008/009); NSC-064 undelivered blocks 078 |
| 10 | NSC-085 + NSC-088: approved, contracts not commit-able | Vincent approved both features 9/15, but each contradicts the current GDD as written | Claude drafts GDD amendments + owner contract revisions; Vincent approves the amendment language | Claude (GDD + contract), Vincent (approve wording), Codex (implement) | NSC-085 needs NSC-084; NSC-088 needs NSC-003/089/091/092 and a structural change to `EnemyTargetKnowledge.cs` |
| 11 | Semi-autonomous admission (parked feature, missed by digest/handoff) | Finished since 2026-09-05, deliberately withheld pending "autonomous mode running clean" — no evidence that trigger has been met | Vincent confirms autonomous mode is stable; Claude rebases and integrates | Vincent (go/no-go), Claude (rebase + integrate) | Autonomous-mode scheduler fixes landing first |

---

## 1. Viewer regression suite repair

**What was asked, by whom, when.** 2026-09-13 ~21:53 UTC (16:53 CT), a Codex Desktop session: "Repair
the full AssistantControl viewer regression suite in an isolated checkout based on exact local main
commit `2eee4670b7b973137d28e4422f9e5b1eee421efa`... Create/use a separate clone/worktree under
`C:\NSC` on a new assistant branch. Do not push or merge." The reported starting defect was
`python -m unittest Pipeline.AssistantControl.test_viewer` → 46 tests, 4 failures, 16 errors.
(Source: `Desktop\nsc-codex-0913-0914-context.md`, rollout
`rollout-2026-09-13T16-53-19-01a09cc2-afd5-7e81-b39a-8b80600bd547.jsonl`.)

**How far it got.** The session's own last reply describes a completed, committed fix: checkout
`C:\NSC\AssistantControlViewerRegression-20260913`, branch
`assistant/viewer-regression-suite-20260913`, commit
`c12f70287bad1b97e66e8e5fbee1710aaa70c33c` (tree `9b17c74710ff214244f2754957ed05974b969749`), on
top of base `2eee4670b7b973137d28e4422f9e5b1eee421efa`. Root cause as reported: shared disposable
Git fixtures still used legacy minimal task contracts, and the viewer's full-graph conformance
reader now requires schema-v2 contracts, so snapshot creation stopped before task rows, simulation
state, checkout authentication and worker projections were produced. The fix added one shared
schema-v2 fixture builder and updated stale assertions (scope exclusion, review alarms,
authenticated controller timing, cold snapshot). **Verified directly:** the checkout still exists;
`git log` inside it shows exactly `c12f70287` on top of `2eee4670b`, and `git status` is clean. The
session itself is marked "LIMIT REACHED (used 99.0%)" immediately after this reply, which is why the
digest calls it unfinished — but the reply text describes a finished, committed fix, not a
half-done edit. What's genuinely missing is independent confirmation that the full 46-test suite
is green on `c12f70287` (only the fix's own description says so).

**Landed on main, or superseded?** **Not landed.** Verified with `git branch --all --contains
c12f70287...` and `git merge-base --is-ancestor` against canonical `C:\NSC\NSC\NoSafeCircle`: neither
the branch nor the commit exists anywhere in that repository (340+ branches checked). Not mentioned
in the graph-lead journal, the reports folder, or Claude's memory as reviewed or merged. Not
superseded by anything else found.

**What remains.**
1. Codex or Claude: re-open `C:\NSC\AssistantControlViewerRegression-20260913` and confirm
   `python -m unittest Pipeline.AssistantControl.test_viewer` is fully green on `c12f70287`.
2. If green, Codex merges it into canonical local main (pipeline tooling, not game content —
   Codex is the one who integrates and publishes canonical main per the standing rule in
   `nsc-background-jobs-throughput-patch.md`).
3. No Vincent action needed unless the fix surfaces a design question.

**Dependencies.** None. Isolated pipeline test-infrastructure work, independent of game content.

---

## 2. Accepted mid-development review fixes (NSC-1165 decomposition reliability)

**What was asked, by whom, when.** 2026-09-13 ~21:19 UTC (16:19 CT), Codex Desktop: "Implement the
accepted fixes from the exact-SHA mid-development review in an isolated checkout. Source
repository: `C:\nscrev\revision-review-integration`. Base exact commit:
`ce9ce1373f120e3bae105d372f2016144d490878`..." The "accepted fixes" are Vincent's relay of Codex's
verdict on the reviewed snapshot (`review/revision-review-mid-20260913` = `ce9ce13`, reviewed in
`C:\nscrev\reports\mid-dev-review-revision-review-20260913.md`): six numbered blockers recorded in
`C:\nscrev\reports\codex-mid-review-blockers-20260913.md` (~21:35 UTC) — outer timeout derived from
effective budgets, accepting advisory-only passes, evidence-depends-on-context rules, a broken
TaskGraph fixture, stronger `needs_human` identity checks, and whole-stack tests. This is
**Pipeline/AssistantControl tooling for the Gauntlet/GER pipeline itself, not game content.**

**How far it got.** This exact session ended "LIMIT REACHED (100%)"; its last reply was mid
scenario-verification ("The bounded revision-review needs_human path passed, including rejection of
the tampered round-3 provider artifact. The run is moving on to the author-correction-at-limit and
forgery cases.") **Verified exact artifact:** checkout `C:\nscrev\codex-revision-review-fixes-20260913`,
branch `codex/revision-review-accepted-fixes-20260913`, HEAD `0a7ac58609a00534f69ff7b4d6c1e5a76b70d654`
("TaskGraph: repair decomposition resource fixture", committed 2026-09-13 16:42:45 -0500) on top of
`bb72b6135b...` ("bind empty GDD evidence to the local Gauntlet", 16:28:20) and `b2d07fbc03...`
("prove the bounded revision review end to end (I1)", 16:22:00), themselves on top of the full
reviewed stack (C0/A/P1/D1C/G). **Plus uncommitted working-tree changes at the moment of cutoff:**
7 files, +263/-49 (`decomposition.py`, `graph_controller.py`, `test_decomposition_needs_human.py`,
`test_decomposition_revision_review_integration.py`, `policy.py`, `prompts.py`,
`decomposition_evidence_guidance_smoke_test.py`) — never committed, still sitting in that working
tree today.

**Important nuance the digest missed:** a **separate, later, more complete pass** (run by "the
coordinating session," not this specific cut-off session) had, by ~00:25 UTC on 9/14, already
produced a fully verified stack covering all six blockers: `C:\nscrev\final-integration`, branch
`throughput/decomposition-final-integration`, head `4fd54b8ce167bd87897926384839b03378e86232`
("A3b" — AssistantControl consumer evidence check plus whole-stack evidence tests), per
`C:\nscrev\reports\final-integration-verification-20260914.md`: **33 of 34 suites green** (the one
non-pass, `test_viewer`'s `GraphControllerTimingEndToEndTests`, is a pre-existing timing flake
identical at `f941857` and `fce5398`, i.e. predates this stack). So the substance of "implement the
accepted fixes" **was finished**, just not by continuing this exact cut-off session — a sibling
effort finished it within a few hours. The `codex/revision-review-accepted-fixes-20260913` WIP looks
largely redundant with it.

**Landed on main, or superseded?** **Not landed**, for either stack. Verified: none of
`4fd54b8c`, `fce5398`, `ff5bdc6`, `4449fb8`, `e25b53e`, `01f2660`, `de46660`, `f7d14b7`, `65a73d0`,
`65e770b` (the final-integration lineage) or `0a7ac58`/`bb72b61`/`b2d07fb` (the cut-off session's
own stack) are reachable from canonical local main HEAD or from any of its 340+ branches
(`git merge-base --is-ancestor` false, `git branch --all --contains` empty for every one). This
whole thread is paused per Vincent's standing rule (`nsc-background-jobs-throughput-patch.md`):
"the Gauntlet stays PAUSED until Astra returns a verdict, Codex not Claude merges and publishes
canonical main." A related but distinct sibling stack (`throughput/assistantcontrol-fixes`, head
`86068e6`) was posted to GitHub Issue #36 and is still awaiting Astra's review as of the last
recorded update (2026-09-13).

**What remains.**
1. Codex/Vincent: decide whether to resume the abandoned WIP or simply adopt the already-green
   `throughput/decomposition-final-integration` (`4fd54b8`) stack, which appears to supersede it.
2. Get Astra's outstanding review/GO on the combined pipeline-tooling stack.
3. Codex integrates the reviewed stack into canonical local main (Claude does not merge or push
   this, per standing rule).

**Dependencies.** Gauntlet stays paused until Astra + Codex sign off. This is Gauntlet/GER
infrastructure, not on the direct critical path for shipping game content, so it is lower urgency
than the NSC-0xx rows below.

---

## 3. Completion-evidence audit for NSC-061/062/066/067/068/069

**What was asked, by whom, when.** 2026-09-13 ~22:41 UTC (17:41 CT), Codex Desktop, read-only:
"Audit NSC-061, NSC-062, NSC-066, NSC-067, NSC-068, and NSC-069 only. Goal: determine why
implemented features remain gray/not_delivered and which can legitimately be made
TaskGraph-conformant from existing committed evidence," against canonical main snapshot
`886bb8169eebd79876ededc4fed940e6cadd1921`. (Source: context.md, rollout
`rollout-2026-09-13T17-41-23-01a09cee-ae47-7312-8f98-0f6e75020831.jsonl`.)

**How far it got.** Session ended "LIMIT REACHED (100%)" after a single user message; the last
reply was mid-analysis with no conclusion for any of the six tasks: "The historical evidence is
uneven. The journals preserve exact filtered test counts for 066-068, but their XML/logs live at
external temp paths and were never committed; the 062 journal explicitly records failed/blocked
validation and pending human review. Git also retains unreachable intermediate candidate commits
named in the journals, which I'm checking against the integrated mainline trees rather than
treating as delivery proof." No report file, evidence directory, or contract edit was produced.

**Landed on main, or superseded?** **Verified directly against current main** (`Tasks/NSC-061.yaml`
through `NSC-069.yaml`, HEAD `22955c5a8`): none of the six has a `Pipeline/TaskGraph/evidence/<ID>/`
directory, so **none has since received a committed delivery/evidence record.** NSC-066 is
independently confirmed still `not_delivered` by the graph-lead journal ("Implemented but visually
unsatisfactory... current TaskGraph state is `not_delivered` because no committed delivery record
exists and Vincent has not passed the title-screen visual gate," journal line 184). Related but
unmerged draft PRs exist from the 9/14 branch push (per `branch-recovery-state.md`): `#129
assistant/foreground-nsc-062-materialization`, `#130 assistant/foreground-nsc-066-title-screen`,
`#132 assistant/foreground-nsc-067-selection` — none merged. The journal separately found
`assistant/foreground-nsc-066-title-screen` **superseded** (its files are byte-identical to main
and still carry the `Color32(16,10,23,255)` solid panel Vincent now wants removed).

**What remains.**
1. Re-run the completion-evidence audit against current main (`22955c5a8`), not the stale
   `886bb816` snapshot — main has moved substantially (NSC-069 alone is now at contract revision 6,
   `576d6733e`, committed 9/15, which changes its acceptance criteria).
2. For NSC-066: the completion-evidence question is moot until the owner contract revision (row 6
   above) lands and a fresh implementation passes Vincent's visual gate.
3. For NSC-061/062/067/068/069: finish the audit; write delivery/evidence records for whichever
   have real committed proof, and state concretely what's still missing for the rest.

**Owner.** Claude for the audit and any evidence-record writing (this touches graph state); Codex
for bulk re-checking test logs/artifacts if there's a lot to sift.

**Dependencies.** NSC-066's audit outcome depends on row 6 finishing first.

---

## 4. The 9/14 orchestrator's "23 should be completed" graph-state repair

**What was asked, by whom, when.** The literal text "23 should be completed" recurs as the user-turn
content across at least four separate compacted turns, all inside one continuous orchestrator
session (`rollout-2026-09-13T19-42-43-01a09d5d-c5f3-7823-b4ab-d0a0ee4b1ca7.jsonl`, "Hi I need you to
take over for as orchestrator," 2026-09-14T00:42:58Z → 15:50:07Z, 292 user messages). The four
"23 should be completed" turns land at 08:44Z, 08:49Z, 08:50Z, and 09:05Z. **Inference** (not
directly stated anywhere I found): this phrasing most likely encodes Vincent's standing complaint/
target that the graph or viewer should show 23 tasks as completed, directing the orchestrator to
true up graph state to match — I could not find an explicit definition of "23" in any source.

**How far it got.** Across the session it produced several small, isolated fixes, each on its own
worktree/branch — **verified still present as linked worktrees of the canonical repo**, each exactly
one commit past its base, **none merged to main**:
- `codex/viewer-instructions-20260914` @ `1db32df46ce1e78576bbc40b5248d2e70e23c84c` — rewrote the
  AssistantControl viewer README and startup guide (live-root port 8828 command, why an isolated
  root shows zero workers, the display-only GER hold file).
- `codex/ger-active-viewer-20260914` @ `8240fedee` — GER viewer runbook change (brown Task Retired
  color, pause-vs-hold semantics, release-to-purple rule); "seven focused viewer tests pass."
- `codex/missing-validation-policy-review-20260914` @ `65ff86439` — NSC-043 recovery: a missing or
  stale validation policy now routes a clean candidate to human review with Unity validation
  explicitly marked "not run," instead of silently implying a pass.

The same session also worked directly on NSC-017 (Unity compile/test-fixture repair) and
re-confirmed NSC-028 was already complete (ran its four encounter-admission tests to record
delivery), before the final cutoff around 14:29-14:30 UTC on 9/14 ("LIMIT REACHED, 100%").

**Landed on main, or superseded?** The three isolated fixes are **verified not on main**
(`git merge-base --is-ancestor` false for `8240fedee`, `65ff86439`, `1db32df46`). **NSC-017's work
did separately land**, but through the independent 9/15-9/16 branch-recovery process, not as a
direct continuation of this session: `codex/nsc017-locked-door-attack-20260914` merged
`1394a3c5b` → `ece05c098` on local main. **NSC-028 was already fully delivered before this session
even started** — `870c5d97d` ("Merge NSC-028 encounter admission cap") and `75672527c` ("Record
NSC-028 delivery evidence") are both already ancestors of current main — so nothing further is
needed there.

**What remains.**
1. Codex/Claude: review and merge the three small, self-contained doc/tooling fixes — low risk,
   nobody has looked at them since 9/14.
2. Claude/Vincent: decide whether a fresh "how many tasks are actually complete" recount is still
   wanted; if so, re-run whatever produced the original "23" figure against current main, since
   branch recovery, GER contract revisions, and the NSC-073/074/093 art merges have all landed
   since.

**Dependencies.** None; independent small cleanups.

---

## 5. The NSC-093 north-east cleaver inpaint trial

**What was asked, by whom, when.** 2026-09-14T14:24:26Z (9:24:26 AM CT): a bounded, review-only
PixelLab correction trial for NSC-093's melee enemy walk animation, targeting the north-east walk
cycle (character `070592db-d334-4e7d-b5c9-5dad404d7f98`, animation group
`1829930f-b534-42f5-ac45-3ca2d0acd9dc`), which showed a duplicate/extra cleaver. (Source: context.md,
`C--NSC/05bc5fc7-429b-4a06-a48e-0c824ec75fb9.jsonl`.)

**How far it got.** **Zero.** The very first reply was "You've hit your session limit · resets
9:30am (America/Chicago)" — no tool was called.

**Related work that did complete, ~08:26-08:27 AM CT the same morning** (worktree/context
`nsc063-melee-ne-single-cleaver-20260914`): a single `inpaint_image` call against the character's
*static rotation reference image* (not a walk-animation frame) successfully erased the extra
screen-left cleaver — job `1486257a-cbd8-4446-810d-36d134054429`, completed, with a download URL
returned. This produced a candidate PNG staged only under
`Docs/Art/Enemies/Candidates/melee_ne_single_cleaver/` (a README, `idle_single_cleaver.png`, a
gameplay comparison, and `rejected_first_inpaint.png`) on branch
`codex/nsc063-melee-ne-single-cleaver-20260914` — **confirmed present and unmerged** in
`C:\nscrev\reports\branch-recovery\waves45-inventory.md` (flagged "NEEDS-HUMAN-EYE... pure
art-candidate staging; needs Vincent's visual call").

**Landed on main, or superseded — and current defect status (inference, well-evidenced by
documents, not by opening the images myself).** The walk-cycle art that *did* merge to canonical
local main (`7d8d98361`/`981002959`, from `codex/nsc093-current-main-review-20260914`, approved by
Vincent on 9/15 after "reviewing the gameplay-scale renders") ships with
`Docs/Art/Enemies/PIXELLAB_WALK_GENERATION.md`, which documents only **two** selected sources: the
original eight-direction batch (group `1829930f...`, used for seven of eight directions, including
north-east) and a separate north-only correction (group `eac8eec0...`). It does **not** list any
north-east-specific correction as selected — the mid-file animate_character regeneration attempt
that targeted the two-cleaver north-east defect is not named as used. So **the double-cleaver
north-east walk defect very likely remains live in the art currently on canonical main.** Vincent's
approval was based on small contact-sheet-scale renders, which could plausibly miss a subtle
duplicate-weapon artifact at that scale. I did not open the actual PNGs to confirm visually — this
is a documented, well-supported inference, not a direct observation.

**What remains.**
1. Vincent: open the current main's melee walk sprites (`Art/Enemies/Source/Walk/...`, or
   `Docs/Art/Enemies/Walk/melee_contact_sheet.png` / `melee_gameplay_scale.png`) and confirm whether
   the artifact is actually visible.
2. If confirmed: Claude runs one new bounded, review-only PixelLab trial (read-only
   `get_character`/`get_image`, plus exactly one `inpaint_image` or `animate_character` call — same
   pattern as the successful prior corrections) targeting just the north-east walk frames, then
   commits the corrected PNGs with `.meta` files.
3. Separately (not blocking): Vincent still owes a visual pick on the parked
   `codex/nsc063-melee-ne-single-cleaver-20260914` idle-art candidate.

**Dependencies.** None; a visual-QA follow-up on already-merged art.

---

## 6. GER refine rounds for NSC-004 (dropped) and NSC-066 (owner contract revision)

**What was asked, by whom, when.** NSC-004 and NSC-066 were the last two nodes in the GER queue's
round-03 ("Codex refine") step, launched ~13:52-13:53 UTC on 9/14; both failed within 1-2 seconds at
14:51-14:52 UTC when the Codex account's usage ran out ("exit code 1; empty or missing OUTPUT.md").
(Source: `ger-queue-state.md` memory + journal.)

**How far it got.** Rounds 01 (Codex generate) and 02 (Claude evaluate) completed for both; no
refined contract exists for either. Packets are intact at
`...\RoomContentGER\<packet>`, snapshot `5b3d0b3a7016-assets-blob`, with `.failed-<UTC>`-renamed
round-03 directories preserved per the documented resume procedure (journal line 655).

**Landed on main, or superseded (verified — journal, 2026-09-15 "GER holds cleared" entry, lines
647 & 668-677).**
- **NSC-004: dropped.** Vincent decided (9/15) it already derives `conformant`; the GER was only an
  optional quality pass. Closed, no resume planned.
- **NSC-066: not resumed via GER.** Vincent instead supplied the design directly from his
  SpaceInvaders project (`C:\NSC\SpaceInvaders`): a mage fleeing an enemy, cycling through 4 mage
  identities against melee and ranged; keep all three taglines; drop the solid background panel so
  the chase shows through. The cheap path is a **direct owner contract revision** (the same
  mechanism already used for NSC-044/049/069/082), not resuming the four-round GER cycle.
  **Verified directly against current main:** `Tasks/NSC-066.yaml` is still contract revision 1 and
  still locks `Assets/NoSafeCircle/DoorPrototype/Scripts/TitleScreenController.cs` and
  `.../Editor/DoorPrototypeSceneBuilder.cs` — **not** `DoorPrototypeGlobalSceneBuilder.cs`, which is
  where the title screen (and the Player GameObject) is actually built, and which is already claimed
  by NSC-039/049/069/075/077. **This revision has not been written yet.** The existing
  implementation branch `assistant/foreground-nsc-066-title-screen` is confirmed superseded (its
  files are byte-identical to main and still carry the unwanted solid `Color32(16,10,23,255)`
  panel).

**What remains.**
1. Claude (GER owner): write the NSC-066 owner contract revision — repoint the exclusive-resource
   claim at `DoorPrototypeGlobalSceneBuilder.cs`, encode Vincent's chase-backdrop/no-panel spec, run
   the independent Sonnet re-check, commit (mirrors the mechanics already used for
   NSC-044/045/046/047/048/049/069/082).
2. Codex/a worker implements against the revised contract.
3. Vincent passes the title-screen visual gate before NSC-066 can be marked delivered.

**Dependencies.** Must land before any implementation starts (the current contract would misdirect
a worker to the wrong file). Shares `DoorPrototypeGlobalSceneBuilder.cs` with NSC-039/049/069/075/077,
so sequencing with those tasks matters.

---

## 7. NSC-015 decomposition returned "revise" (from the 9/16 handoff)

**What was asked / what happened.** Per the handoff (`C:\NSC\nsc-handoff-20260916.md`, "Other open
items"): "NSC-015 decomposition: the reviewer returned 'revise', because the candidate weakened the
parent's validation gates." This is taken as a verified fact from a primary source I was given, but
I could not independently locate the exact run's packet or reviewer output in the journal, reports
folder, or memory searched — **treat the run's exact location as unverified**, though the fact
itself (source: the handoff) is trustworthy.

**How far it got (independently verified background).** NSC-015 ("Melee Enemy Pursuit, Close-Range
Attack, and Gameplay Prefab") was committed as contract revision 6 (`6fb702b579875afcc0d7955b94c790fe7b0bd821`)
on 9/14 under `commit_contract_then_decompose`, then held as "decomposition queued" (journal lines
364-366; `ger-queue-state.md`). Its D1B.2 review-only decomposition launch was **refused twice by
Claude's auto-mode permission classifier on 9/14** (13:46 and 14:40 UTC) because it needs provider
spend — it never actually ran that day. The 9/15 journal entry classifies NSC-015 as group E:
"committed but awaiting decomposition... the two-way split was proposed and never applied...
deliberately not made purple." The "revise" verdict the handoff cites must therefore come from a
D1B.2 run some time after 9/15, once Codex had capacity again (confirmed available per
`ger-queue-state.md`'s 9/15 "Codex quota correction" note).

**Landed on main, or superseded?** Not committed — `Tasks/NSC-015.yaml` is still at the pre-split
revision 6 shape; no revision-7 split was found on main.

**What remains.**
1. Codex: redraft the decomposition so the child split no longer weakens the parent's validation
   gates.
2. Claude: re-review the corrected split (a D1B.2 review-only call).
3. Claude, once `review_ready`: apply the reviewed split through the supported graph path — this is
   explicitly the GER owner's job (see `ger-owner-role-commits.md` / `ger-owner-makes-design-decisions.md`),
   needing Vincent's exact-plan authorization per AGENTS.md:60.

**Dependencies.** NSC-015 sits in the "spells and enemies" GER wave with NSC-007/008/009/017/052/
053/054/088. NSC-033's reset child depends on NSC-015's prefab child (journal line 362), so NSC-033
work is also gated on this landing.

---

## 8. NSC-039: floor visuals wrong, door sorting broken (from the handoff)

**What was asked / what happened.** Two separate defects Vincent reported while running main on
9/15, both explicitly deferred to the level rebuild rather than patched now (journal lines 678-688).

- **Floor rendering:** a harsh dark/light diamond-checker floor with a blown-out gradient band at
  the wall seam and no visual continuity with the brick wall tiling — not yet diagnosed, not fixed.
  Related prior art: the NSC-042 wall-tiling defect, where a missing pixel-check let visually wrong
  tiles pass (see Claude memory `nsc-042-wall-tiling-root-cause.md`).
- **Door sorting/rendering:** sorting order is wrong on doors — this already belongs to **NSC-039
  World-Space SpriteRenderer Prefab and Sorting Foundation**, whose AC-001 already covers doors and
  which already claims `DoorPrototypeSceneBuilder.cs`, `DoorPrototypeGlobalSceneBuilder.cs`,
  `DoorPrototypeSceneBuilderTests.cs` and `Assets/Scenes/DoorPrototype.unity` — don't open a new
  task. Separately, the doors currently in-game are still primitive placeholders: 7 committed door
  sprites (`Art/Doors/Source/door_bonestone_*.png`) are referenced by **zero** scenes or prefabs
  today.

**Landed on main, or superseded?** Not fixed; deliberately deferred by Vincent's own instruction.
NSC-049 revision 5 (`df90eb340`, already on local main) already names "NSC-065 textured doors" in
its batched room refresh as the integration point. Unmerged branches hold more door art than main:
`codex/nsc065-retained-art-review-20260914` adds 8 further door PNGs beyond what's on main; which
door set is canonical is an open Vincent visual pick.

**What remains.**
1. Whichever room task rebuilds its scene (the NSC-044-049 family) must treat floor material/tile
   alignment as in scope, and the composed-scene camera review should fail on a checkerboard floor.
2. NSC-039 does the actual sorting-order fix and wires in real door sprites in place of primitives.
3. Vincent picks the canonical door-art set among the unmerged NSC-065 branches.

**Owner.** Codex/worker for implementation; Vincent for the door-art visual pick.

**Dependencies.** Needs the room rebuild (NSC-044-049, NSC-049 rev 5) to land first; NSC-041 (door
hover/selection feedback, released `release_without_change`) will interact with whatever sprite
wiring lands.

---

## 9. Claude's design decisions for NSC-007, 008, 009, 030, 078

**What was asked, by whom, when.** Vincent delegated these five design-question sets to Claude
directly on 2026-09-15 ("The remaining design questions (NSC-007, 008, 009, 030, 078) are delegated
to Claude to decide, not to return as questions" — journal line 671), after each came back
`needs_design` from its GER round-04 re-audit on 9/14.

**How far it got.** A complete, code-verified evidence pack was finished 2026-09-15:
`C:\nscrev\reports\design-decisions\seven-task-evidence.md` (385 lines, covering these five plus
NSC-085/088 — see row 10). For each task it independently re-derives, from direct GDD/code reads
(not just quoting the GER audits): every open design question, whether the GDD actually answers it
or is silent, the current code state, and dependency/file-ownership conflicts. Highlights:
- **NSC-007 (Fireball) / NSC-008 (Frost Field) / NSC-009 (Force Wave):** all three share the same
  unresolved input-binding question (D1) and the same title-screen-suspension gap (nothing
  currently re-enables a spell after the title screen suspends it — confirmed by direct read of
  `TitleScreenController.cs` and `WizardGameEntryController.cs`). Frost Field is additionally
  blocked on a second team's not-yet-built interface (`NSC-013`/`ActiveEnemyRegistry.cs` has no
  spatial query at all). None of the three has any component code written yet.
- **NSC-030 (encounter placement):** decisions 1/2/5 (pending-enemy policy, ranged-under-cap
  ordering, Chapel spawn-to-cover) change contract text; the runtime foundation
  (`EncounterAdmissionController.cs`, `ActiveEnemyRegistry.cs`) already exists and is tested — only
  per-room content is missing.
- **NSC-078 (prop art):** blocked mainly on an ownership split with NSC-064 (undelivered) over which
  task owns base architecture pieces (floor/wall/corner/pillar/etc.) — a genuine unresolved overlap,
  not just a GDD silence.
- **This is the largest single remaining piece of design work in the whole backlog** — as of the
  last available journal entry (9/16), **no decisions have actually been written into any
  contract yet.**

**Landed on main, or superseded?** Not applicable yet — nothing has been decided or committed for
any of the five.

**What remains.**
1. Claude actually writes the decisions into owner contract revisions, one per task (same mechanic
   as NSC-044/045/046/047/048/049/066/069/082), with an independent re-check before commit.
2. Given the interlocking nature (shared `InputSystem_Actions.inputactions` lock across
   NSC-003/007/008/009; the shared title-screen-suspension gap across 007/008/009; the NSC-064/078
   ownership split), these should likely be decided as a batch, not independently.
3. Codex implements afterward.

**Dependencies.** NSC-013 (undelivered) blocks Frost Field's downstream interface even after design
questions are answered; NSC-064 (undelivered) blocks NSC-078.

---

## 10. NSC-085 and NSC-088: approved, but contracts still can't commit

**What was asked, by whom, when.** Vincent approved both features on 2026-09-15: "NSC-085 side-
chamber wing: approved" and "NSC-088 Spectral Decoy: approved" (journal lines 669-670). Both had
come back `needs_design` from GER on 9/14.

**How far it got.** The same `seven-task-evidence.md` pack covers both in full. The core finding for
each is a **direct conflict with the current GDD text**, not merely an open question:
- **NSC-085 (side-chamber wing).** GDD line 560 authorizes only "one additional room" as a stretch
  goal; GDD line 558 explicitly excludes "multiple floors"; GDD lines 143-149 (the blockout) exclude
  new rooms outright. NSC-085's own acceptance criteria describe something categorically larger —
  branching paths, a hub junction, at least one loop, optional dead-end reward rooms. **A GDD
  amendment must happen before this contract can be anything but a design hold** (this is decision 2
  in the GER round-04 recommendation, and the journal separately recorded it as NSC-085's "core
  blocker" back on 9/14).
- **NSC-088 (Spectral Decoy).** GDD lines 526-537 state the current pursuit model explicitly and
  exclusively: an enemy always tracks the wizard, acquisition/loss are governed purely by distance
  and a bounded random search, and crossing a doorway does not clear pursuit. Nothing in the 739-line
  GDD describes retargeting to a second object. Vincent's own direction ("draw pursuing enemies
  after it... slip past while they chase the phantom") requires an actual GDD amendment. Code-side,
  confirmed by direct read: `EnemyTargetKnowledge.cs` is structurally single-target (one
  `wizardTransform` field, no branch point for a second candidate anywhere in its 151 lines) — this
  needs a real structural change, not a bolt-on component.

**Landed on main, or superseded?** Not committed. Both remain at their pre-GER-cycle contract
revisions (NSC-085 revision 2, NSC-088 revision 3), both still with empty or placeholder
`exclusive_resources`/`completion_gates` reflecting their design-hold state.

**What remains.**
1. Claude drafts the specific GDD amendment language for each (same mechanism already used for the
   GDD §6 shelf-height revision, `c326a0f59`, already on main) — how large the NSC-085 wing may be
   and where it attaches; what mechanism lets NSC-088 redirect pursuit.
2. Vincent approves the exact amendment wording.
3. Claude writes each task's owner contract revision, independent re-check, commit.
4. Codex implements, including — for NSC-088 — the structural change to `EnemyTargetKnowledge.cs`.

**Dependencies.** NSC-085 depends on NSC-084 (undelivered) and must not become a bottleneck for the
required five-room content work (its own AC-004 already says so). NSC-088 depends on
NSC-003/089/091/092 (none delivered) and would be a fifth claimant on the already-contested
`Assets/InputSystem_Actions.inputactions` file (currently locked by exactly NSC-003/007/008/009).

---

## 11. Other half-finished work the digest and handoff missed

### 11a. Semi-autonomous admission branch (parked since 2026-09-05)

**What it is.** A finished feature — gate architect admissions behind switchable operator approval —
deliberately **not** integrated. Vincent's instruction (2026-09-05): wait, and integrate only after
autonomous mode is working right end-to-end. Source: Claude memory
`semi-autonomous-admission-pending-integration.md`.

**Verified current state.** Checkout `C:\NSC\ClaudeSemiAutonomous-20260905\NoSafeCircle` still
exists, branch `claude/add-semi-autonomous-admission`, exactly one commit `aac9b96` ("Gate architect
admissions behind switchable operator approval"), working tree clean, never pushed anywhere. 6,534
insertions across 11 files, authored against a base now far behind current main.

**Why the digest/handoff don't mention it:** it predates the 9/13-9/14 window and wasn't touched
during it — it is simply still sitting exactly where it was left. I found no journal or memory
entry since 9/5 stating that "the ten-task autonomous gauntlet runs clean end to end," which is the
stated trigger condition for integration.

**What remains.**
1. Vincent confirms autonomous mode has since run clean (or decides it now has).
2. Claude rebases the feature branch onto current main and integrates, preserving the two
   non-negotiable acceptance criteria: the admission gate must default OFF (a run resumed with only
   `-RunId/-ConfirmRepository/-CheckoutRoot/-Source` must behave exactly as today), and it must not
   change an existing run manifest's sha256 or break resuming a pre-existing run.

**Owner.** Vincent (go/no-go call), Claude (rebase + integration).

**Dependencies.** The autonomous-mode scheduler fixes it was deliberately kept separate from must be
stable first, to avoid rebasing a 6,500-line branch repeatedly and masking scheduler regressions.

### 11b. Two nuances already folded into the rows above, flagged again here for visibility

- **Row 2** undercounts progress: a fully finished, 33/34-green version of the "accepted mid-dev
  review fixes" work already exists (`throughput/decomposition-final-integration` @ `4fd54b8c`), it
  is just sitting unmerged like the cut-off session's own WIP.
- **Row 5**'s art defect (NSC-093 double cleaver) is inferred still-live on current main from the
  shipped generation doc's own bookkeeping, not from opening the sprite files — worth a two-minute
  visual check before spending a PixelLab call on it.
