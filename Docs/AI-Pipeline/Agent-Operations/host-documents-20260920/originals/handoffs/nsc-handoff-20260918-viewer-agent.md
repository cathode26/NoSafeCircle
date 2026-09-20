# Handoff: Viewer Agent, 2026-09-18

Retiring at 415k/1M tokens (42%), per Vincent's new policy in CLAUDE.md "Don't waste tokens" (message cost = receiver's whole context on wake-up). Nothing was wrong with the session; this is routine.

## Where things stand

Everything here is volatile — re-derive it, don't trust the value below past the moment you read this:

- `python -B C:\nscrev\viewer-tools\nsc_viewer.py status` — as of 2026-09-18 09:56 UTC: pid 33480, live pair, `inspection_error: null`, HEAD `2559514826e9` (moved twice already this session; local main was ahead of origin, one push happened mid-session at `a71849dc5`, more commits landed after). **If it's healthy, don't restart it** — the "was it ever down" question below is separate from "is it down now."
- `python -B C:\nscrev\viewer-tools\nsc_viewer.py overlays` — as of last check: held = NSC-030, NSC-088 (both legitimate — 030 sequenced after room layout, 088 active GER), no expired working markers. Human-complete list is fully audited (see below) — don't re-audit it from scratch, re-run the audit script instead if you need a fresh pass (see Pointers).

## Done this session (full detail in the journal, search "Viewer Agent")

1. Started the viewer twice this session — both times it was simply gone, no crash log either time. **Open unknown, not a closed one:** I restarted and moved on, I never root-caused why it died. "Restarted, fine" is not the same claim as "investigated, fine" — treat the underlying cause as unknown, not ruled out, if it happens a third time.
2. **Full audit of every human-complete overlay marker** against contract git history: pulled 3 stale ones (NSC-069, NSC-040, NSC-066 — all later confirmed correct by GER Agent/taskcontrol), left the rest (real conformant evidence or contract genuinely unrevised).
3. **Graph evidence-debt audit**, Vincent asked by name: `C:\nscrev\reports\viewer-agent\evidence-debt-audit-20260918.md`. Split 50 not_delivered tasks into evidence-debt/partially-built/not-built/uncheckable, ranked a ready queue. Caught and fixed two of my own errors (a wrong record-binding recommendation, a mis-counted "23 of 25" that was actually 15) — GER Agent credited the self-correction. Same night: GER cleared 9 of the 15 validation-policy gaps (2 by writing entries, 5 more the "cheap" bucket I split out, 1 turned out already-present). **7 remain, GER's queue: NSC-032, 040, 050, 051, 060, 061, 067** — don't redo this analysis, it's GER's now.
4. Diagnosed two live "why isn't it blue" questions during Vincent's filming night (NSC-097 stopped 43s after dispatch — real, not a bug; the 30s snapshot cache can miss a very short run). **Wrote both findings into `nsc-viewer-agent-guide.md` section 6 myself** (Documentation Agent confirmed this is a standing-OK factual update, no need to ask Vincent) — also fixed the guide's own bad advice (it said "grep the `status` field", which is the wrong field and caused two agents' mistakes that night; now points at `worker.status` with the source-verified color logic).
5. Handed a display bug to Pipeline Maintainer: human-complete overlay can override an aggregate/decomposed-parent state (evidence: NSC-066). Board row **H-20260917-30**. Also asked for GER-in-progress to get its own legend entry separate from real "cancelled" — Pipeline Maintainer accepted, queued behind their current jobs, same board row.
6. **Pre-filming health check (2026-09-18 03:03 UTC, ahead of the NSC-007 recording)**: ran status/overlays/watch, confirmed healthy and clean (live pair, `inspection_error: null`, held = NSC-030/078/088 all legitimate, no stale overlays), reported "clean, nothing needed restarting" to Documentation Agent. No restart happened — it was already healthy at that check.

## Rules still in force

- Section 3/4/4a of the guide: overlay-only changes, quote Vincent's exact words for `complete`, verify done/not-done actively (this is now standing duty, not a one-off), new task intake flows through me (draft only if Vincent asks or I ask him first).
- Pause exception: Release Agent's requests get done immediately even if Vincent pauses the team.
- No Codex until 2026-09-22 18:55 local; Gmail Claude account first for any bulk lookup.

## Open items / waiting on nobody in particular

- Board row H-20260917-30 (Pipeline Maintainer, GER-legend-entry + aggregate-override bug) — no ETA given, not urgent.
- GER Agent's 7-task validation-policy queue — theirs, just watch for the next `ger-finish` requests as they land.

## Transcript review pass (2026-09-18, Vincent's full 5-pass procedure, guide section 3a)

Ran `nsc_session_digest.py digest --session 99beff7b-cdbc-4cbd-bbf7-06662e97534b --scale 5` (needed scale 5 to avoid truncating sections 3/5 — the default budget omitted up to 22 of 31 peer messages). Job corpus: `C:\nscrev\reports\viewer-agent-job-corpus.md`, 48 messages, Vincent and peers merged chronologically. A first, incomplete version of this pass ran earlier the same session (4 passes, no corpus, no stranger test) — this supersedes it.

### Open ideas
None found, both passes. Section 2 grepped clean for `maybe|eventually|later|we should|do we need|what if|I think we` across all 17 of Vincent's messages — no unresolved "should we" sitting untouched.
- ~~GER-legend-entry fix (GER-active shouldn't share "Task Retired" with real cancelled tasks)~~ — **CLOSED as far as my side goes**: handed to Pipeline Maintainer, accepted, board row H-20260917-30. Still open on *their* side, not mine — check the board row for status, don't re-propose it.
- ~~Aggregate-override display bug (human-complete overlay can mask a decomposed-parent state, evidence NSC-066)~~ — **CLOSED as far as my side goes**, same board row H-20260917-30.

### Queued but never built
- ~~"I'll confirm blue lands" on the NSC-046/NSC-007 filming-night dispatch (told to Game Agent, never followed up)~~ — **CLOSED, found and closed by this pass**: NSC-046's worker was stuck at `ready_pending` from that original dispatch, unresolved for hours, likely holding a lease. Told Game Agent directly. **Then Game Agent + Pipeline Maintainer found the real root cause** (see next item) — this is no longer an open thread for me, just background if the same symptom recurs on another task.
- **New, from Game Agent/Pipeline Maintainer, not yet closed:** `retire-worker` archives `worker` and pops it but never touches `launch`; `worker_control._worker` falls back to `launch`, so a retired run reports `ready_pending`/host-dead forever — **the viewer is one of four readers (worker_control, result_inspection, viewer, graph_controller) that currently disagree about one record.** Pipeline Maintainer is rewriting retire and adding a shared `current_attempt(record)`, plus a one-time repair script for already-retired records like NSC-046. **Open action for whoever holds this role next: re-check the viewer's projection on any stuck-`ready_pending` task once that fix + repair script lands** — this is a genuine "come back to it" item, not a closed one. Board row **H-20260918-07** already tracks the underlying `retire-worker`/`launch` defect (I found it by grepping BOARD.md while writing this, not by memory — worth the habit) — `refresh-prepared` and `start-worker` are noted "both since fixed" there, but the viewer's own re-check isn't mentioned in that row, so it may still be genuinely open. Confirm against the row's current text, not this summary.

### Outbound claims that proved false
Both already corrected in the audit report and told to the recipients — no new ones surfaced by this pass.
1. Told GER Agent to write NSC-089's delivery record "against `4047a4335`" — wrong, `record_delivery` requires `HEAD == validated_commit`, the historical commit belongs in notes as provenance only (NSC-069 precedent). Game Agent caught it independently; I corrected the report and told both.
2. Wrote "23 of 25 evidence-debt tasks have no validation-policy entry" in the first draft of the audit report — real number was 15 (miscounted, not a data error). Caught it myself before GER Agent acted on it, corrected the report.

### Communication profile (from the 48-message corpus)
- **Bursts, not paragraphs.** When Vincent has something complex to say, he sends 3-5 short messages in quick succession (e.g. 06:38-06:50 UTC, four messages building one instruction; 07:17-07:18, a policy statement then an immediate scope correction) rather than one long one. Read a burst as one thought — don't act on message 1 of 4 before the rest land, if they're arriving within the same minute or two.
- **"typed while busy" messages are real, not noise.** He keeps typing follow-ups while I'm mid-task (marked in the digest); the follow-up can narrow or redirect the original ask (e.g. "This was meant for the documentation agent more than you :)" arrived one minute after a message that looked squarely aimed at me). Check for a newer message before finishing a task that started from an older one.
- **Bare acknowledgments mean stop, not continue.** A lone "ok" or "It works now" closes the exchange; it's not an opening for more detail unless something changed.
- **Terse questions want the fact, not the reasoning.** "What port is the viewer on?", "ip and port?", "Why do we have 2 retired tasks?" — answer the literal question first (the number, the port), reasoning after only if asked. He's usually reading a number or label directly off the UI and wants it reconciled against real task IDs, not a category explanation.
- **Casual profanity or a bare emoji is tone, not a request.** "Well we ran out of fucking tokens on codex ;(" and "the shoot is done, it failed 🙂" are both venting/light-tone, not asking for management or sympathy — a short factual acknowledgment is the right register, not reassurance.
- **He corrects scope out loud rather than silently.** When a message was misdirected or a prior instruction was wrong, he says so plainly and immediately ("This was meant for the documentation agent more than you", "your guide has a new section 4a" superseding the launch prompt) rather than letting it stand. Take a correction as authoritative over whatever it replaces, including things I was told at session start.

## Pointers

- Guide: `C:\NSC\nsc-viewer-agent-guide.md` (section 6 rewritten tonight, section 2 now lists the audit script — read it fresh, don't rely on an old copy).
- State file: `C:\NSC\agent-state\viewer-agent.md` — kept current all session, has more detail than this file on every item above.
- Journal: search `.assistant-control\graph-lead-journal.md` for "Viewer Agent" for the full timeline.
- Evidence-debt audit: `C:\nscrev\reports\viewer-agent\evidence-debt-audit-20260918.md`. Re-runnable script (fixed to a durable output path tonight, was pointed at my ephemeral scratchpad before): `C:\nscrev\viewer-tools\audit_evidence_debt.py`, writes `C:\nscrev\viewer-tools\audit_raw.json`.
- Job corpus (every message this session, chronological): `C:\nscrev\reports\viewer-agent-job-corpus.md`.
- One operating pattern worth keeping, not written as a rule anywhere: when a finding affects two agents' work, notify both directly and in parallel rather than routing through one relay — faster, and low-risk since neither can act on the other's authority. Used it repeatedly tonight (GER + Game Agent on evidence debt; Pipeline Maintainer + Documentation Agent on separate findings).
