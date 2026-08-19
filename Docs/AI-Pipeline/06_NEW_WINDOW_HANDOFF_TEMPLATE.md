# New Window Handoff Template

Attach `00_MASTER_CONTEXT.md` plus the ONE milestone context relevant to the work, then use this prompt:

---

We are continuing development of the autonomous AI pipeline for the Unity game No Safe Circle.

Repository:
https://github.com/cathode26/NoSafeCircle

Read the attached context file(s) as the source of truth for the subsystem we are working on in this window.

Important constraints:

1. Do not redesign the whole pipeline unless this milestone reveals a blocking architectural problem.
2. Work on the milestone/subsystem described in the attached context.
3. Prefer deterministic local Python/Git/Unity tools over LLM reasoning for factual/computational work.
4. Persistent state must live in the repository or GitHub, not only in this conversation.
5. Keep Claude work bounded to one ticket at a time.
6. Do not silently absorb newly discovered substantial dependencies into an existing ticket.
7. Before ending this window, create/update a concise repo handoff artifact describing what was built, commands, changed files, known limitations, and the exact next step.

First inspect the current repo state relevant to this milestone and tell me what already exists versus what still needs to be built. Do not start making changes until we agree on the first implementation slice.

---
