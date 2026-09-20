# Decomposition Agent job corpus — 2026-09-17/18 session

Every request received, numbered, in order. Source: session digest `C:\NSC\agent-state\decomposition-agent-20260918-0421-b936e9cb.md`, sections 2-3. Built at 95%+ context, so this is drawn from that digest, not a fresh re-read of the transcript — treat as reliable for content, not necessarily exhaustive of every peer message (92 total arrived; the digest itself keeps the newest and omits the oldest, noted per section).

## From Vincent (29 total, 1 typed-while-busy sample below marked)

1. Launch prompt: "You are going to be the decomposition agent. C:\NSC\agent-state\decomposition-agent.md Please read here." — ACTIONED (read it; file didn't exist yet, bootstrapped from launch prompt + roster).
2. "Try to decompose 015, if it fails you will need to figure out why. We failed on 15 before so maybe you can investigate into why it failed and then try to fix it so decomp will be successful when you run it?" — ACTIONED (extensive investigation + eventual success).
3. "wait for the Pipeline Maintainer's P18 fix" — ACTIONED.
4. "Are you using a mixed provider to do this so codex is doing some of the work?" — ANSWERED.
5. "go for the paid decompose run" — ACTIONED (NSC-015 launch).
6. "Hi what do you need from me? 🙂" — ANSWERED.
7. "You cant do decompose on a branch?" — ANSWERED, led to design thread.
8. "Tell our pipeline maintainer agent to fix it so you can do decompose on a branch." — ACTIONED (relayed).
9. "Im confused why cant an isolated clone be used?" — ANSWERED.
10. "We allow local runs so we are not sharing mains task graph but a copy of it. We should be able to do decomposition completely in the branch on our own tasks and merge into main." — ACTIONED (relayed refined spec to Pipeline Maintainer).
11. (typed while busy) "Can you have pipeline maintainer Agent ask you if what I am asking for is supported. If it is, then that should be the primary way for you to do your decomp, and then the documentation agent should update the documentation on that topic." — ACTIONED (relayed full sequencing).
12. "Okay so they said for you to just try it in a branch and see how it goes?" — CORRECTED (no, not ready yet).
13. "okay it is a ton of work to do part 2, so freeze main for 12 minutes so you can do your decomp :)" — ACTIONED (NSC-015 success).
14. (typed while busy) "shoot is over, we failed" — ACKNOWLEDGED (quiet mode had already been signaled by a peer relay; this was his own direct confirmation).
15. "go" — ACTIONED (NSC-007 launch).
16. "Are you having trouble running or blocking commits a lot?" — ANSWERED honestly.
17. "Im just trying to understand how necessary it is to let you work on a branch" — ANSWERED.
18. (typed while busy) "ok we can wait" — ACKNOWLEDGED.
19. "Do we allow 3 way splits?" — ANSWERED (verified from source, not assumed).
20. "use a smarter agent to split the task" — ACTIONED (found NSC_CLAUDE_MODEL mechanism, Opus escalation).
21. "awesome, hopefully opus will succeed" — ACKNOWLEDGED.
22. "How is decomp going?" — ANSWERED (status check).
23. "What did it decompose into?" — ANSWERED (about NSC-015 initially, since it was the only one with a real plan at that point).
24. "I mean 007" — CORRECTED to the actual referent, answered.
25. "Tell Fable this problem and ask them how they would fix decomposition so it would work." — ACTIONED (spawned Fable subagent, relayed full findings).
26. "So what did you change to get it to work?" — ANSWERED honestly (credited the GER Agent's contract fix, not my own escalation, as the actual fix).
27. "So we need to add this as a todo when things go wrong. Can you tell the documentation agent, it means we need to update what the decomposition agent should do when things go wrong." — ACTIONED (relayed with specific proposed wording; Documentation Agent updated guide 1b).
28. "Before you retire, run the full handover pass..." (this message) — PARTIALLY ACTIONED: corpus built (this file); full 5-pass + stratified stranger test + fix cycle handed to a successor, see handoff file, due to context (95%+ when received).

## From peer sessions (representative — the digest keeps the newest 11 of 92; earlier ones are not reproducible from what I have)

1. GER Agent, 08:04-ish equivalent, "ESCALATION LADDER: rung 3 is unsafe from 2026-09-22" (later corrected to 2026-09-19, two separate Codex accounts) — ACTIONED (recorded in guide/memory/handoff).
2. Documentation Agent, "READ CLAUDE.md Don't waste tokens... Check yours now" — ACTIONED (checked usage, began retirement planning).
3. Documentation Agent, "DECIDE handoff contents... what would a successor of yours lose" — ANSWERED (6 bullets sent).
4. Documentation Agent, "RETRY NSC-007 against rev 8" — ACTIONED, but the diagnosis in the message ("not duplication") was itself corrected two messages later.
5. GER Agent, "YOU WERE RIGHT on c" (multiset arithmetic correction) — ACKNOWLEDGED.
6. Documentation Agent, "DO transcript pass, add to your handoff" — ACTIONED (this session).
7. Documentation Agent, "DONE — guide 1b updated" then "CORRECTION: it is done now" — ACKNOWLEDGED both.
8. Documentation Agent, "NEW final step after your handoff: test it on a stranger" — ACTIONED (Explore subagent, found real NSC-015 staleness).
9. Documentation Agent, "UPGRADE to the stranger test... Pass 5" — PARTIALLY ACTIONED (noted in handoff as a successor task, not run myself — context).
10. GER Agent, "Vincent approved the NSC-007 plan... approve 007" — RECORDED, NOT ACTED ON (did not independently confirm with Vincent directly nor apply, due to context; explicit note in handoff for successor).
11. Documentation Agent, "CORRECTION: Codex returns TOMORROW" (two-account clarification) — ACKNOWLEDGED, already reflected correctly in handoff.

## Note on completeness

This corpus was built from the digest's retained window (newest-first-kept), not a full 92-message reconstruction. A successor with more context budget should consider re-running the digest and cross-checking peer message counts if a truly complete corpus matters for their purposes.
