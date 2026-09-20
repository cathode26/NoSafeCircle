# Fleet state

**What this is.** One page holding what every agent is doing right now, so nobody rebuilds the picture from
messages. It is the source, not a copy: if something here contradicts a guide, the guide wins on *how* and this
file wins on *what is happening*.

**How this file works.** Two kinds of content, and the difference is the whole point:

- **Re-derivable facts** — anything a command can answer. Those are *commands here*, not values, because a value goes stale silently.
- **Per-agent state** — **only its owner writes its block.** One author restating seven agents' state is how this file's first version
  shipped with a wrong line within the hour. If your block is missing, that is correct: read that agent's own file instead.

---

## Next session: a coordinated fleet cleanup

**Vincent, 2026-09-19 at shutdown:** *"When we are running again I think we will need to work with the clean up agent together and get our project in shape, because its a wreck."* and *"Like as a team with everyone"*.

**Every agent is in this, not just the Cleanup Agent, and it waits for him to say go.** Read your own todo file for your part. Two things are already known and constrain it: the junctions under `C:/nscrev` are **load-bearing** (live code resolves through one), and `C:/NSC-History-20260918` **cannot be deleted unread** — see runbook rules 21 and 22.

---

## Re-derive, don't read

```bash
git -C C:/NSC/NSC/NoSafeCircle log -1 --format='%h %s'      # canonical main (moved ~10x in one night)
docker ps --format '{{.Names}} {{.Status}}'                  # what is actually running
python -B C:/NSC/NSC/NoSafeCircle/Pipeline/TaskGraph/taskcontrol.py states
claude -p "/usage"                                           # which account, and how much of the week is left
claude auth status --text                                    # host CLI account - it has changed mid-day before
```

Viewer: `http://127.0.0.1:8828`. Nothing is pushed to origin; local main is far ahead by design.

---

## Where each agent's truth lives

**Two kinds of file per agent, and you usually want both.** A `nsc-handoff-*` file is **point-in-time** - written once at retirement and
never updated. An `agent-state\*` file is **live** - the running log its owner keeps current. **Read the state file for what is happening
now and the handoff for what changed at retirement.** Reading only the handoff under-reads a live agent.

| Agent | Point-in-time handoff | Live state file |
|---|---|---|
| Game Agent | `C:/NSC/nsc-handoff-20260918-game-agent.md` | `C:\NSC\agent-state\game-agent.md` |
| GER Agent | `C:/NSC/nsc-handoff-20260918-ger-agent.md` | `C:\NSC\agent-state\ger-agent.md` |
| Art Director | `C:\NSC\nsc-handoff-20260918-art-director-agent.md` | `C:\NSC\agent-state\art-director-agent.md` |
| Pipeline Maintainer | `C:\NSC\nsc-handoff-20260918-pipeline-maintainer.md` | `C:\NSC\agent-state\pipeline-maintainer-agent.md` |
| Decomposition | `C:\NSC\nsc-handoff-20260918-decomposition-agent.md` | `C:\NSC\agent-state\decomposition-agent.md` |
| Viewer | `C:\NSC\nsc-handoff-20260918-viewer-agent.md` | `C:\NSC\agent-state\viewer-agent.md` |
| Release | `C:\NSC\nsc-handoff-20260918-release-agent.md` | `C:\NSC\agent-state\release-agent.md` |
| Documentation | `C:\NSC\nsc-handoff-20260918-documentation-agent.md` | `C:\NSC\agent-state\documentation-agent.md` |

**All eight roles now have a handoff.** Game Agent and GER wrote theirs at 05:05, twenty minutes after this table claimed they had none - a line that was already wrong when written, which is why this file points at files instead of restating what is in them.
**Correction 2026-09-18:** this file previously said Decomposition had no state file. It does - `C:\NSC\agent-state\decomposition-agent.md`, 99 KB, last written 03:28 - plus a second dated copy, `decomposition-agent-20260918-0421-b936e9cb.md`. Checked with `ls`, not recalled.
**Cleanup Agent is running, created 2026-09-18** (declined and reinstated the same evening: `"no clean up agent"`, then `"We need a clean up agent"`). 58 GB under `C:\NSC\_worktrees` awaiting triage.

---

## Owner-written blocks

*(Empty by design. Each agent appends its own block here — under ten lines, with a `verified` stamp. A block written by
anyone other than its owner should be deleted, not corrected.)*

---
## Dated triggers

| When | What |
|---|---|
| ~~2026-09-19~~ **FIRED 2026-09-20**, then **2026-09-22 18:55 local** | **(a) DONE: the all-Claude routing is lifted** — Vincent's own word, 2026-09-20; `CLAUDE.md` and `nsc-codex-jobs-guide.md` updated, memory `codex-quota-out-until-20260922` rewritten rather than deleted because the **second** account still resets 2026-09-22 18:55. **(b) Still open:** the mixed-provider `--env` rung — `claude,codex` pools only on the same-provider path, so verify `actual_model` before trusting it. **(c) Still open:** the record-level undo design goes to Astra. |
| `run_job.py` review passes - **NOT YET: FIX FIRST, 2026-09-18** | Fable review reproduced 3 blocking bypasses (clone guard accepts `\\?\` and UNC spellings of the canonical repo; `--allow-tool` injects Write/Edit/Bash verbatim into read-only job types; the 24h account cache fails open). Report `C:/nscrev/reports/run-job-review-20260918.md`. **Hold**: do not point `nsc-codex-jobs-guide.md` 4.3 at it until the Pipeline Maintainer sends an APPROVE |
| `propagation_check.py` review passes - **NOT YET: FIX FIRST, 2026-09-18** | Fable review reproduced 3 blocking findings: every step but the symbol diff reads the **checked-out tree** rather than `<head>`, so the "on main, about to merge" case reports 0 selected and exits 0; a changed test file is never selected for itself (PR #134 round 4); method-level renames are invisible (PR #134 round 1). Report `C:/nscrev/reports/propagation-check-review-20260918.md`. **Hold**: runbook rule 2 and the main-orchestrator and steward merge steps keep the manual grep until an APPROVE arrives |
| `new_task.py` lands | Write the "add a task" procedure into the Viewer Agent's guide |
| Cleanup Agent session created | **Done 2026-09-18** — session running; added to `CLAUDE.md`'s agent list. |

---

## Standing numbers worth not re-deriving

- **Crew peak memory: 381 MB**, reported by the Game Agent as sampled every 15s across a full run. **Unverified: no report path or run id was recorded, so a reader cannot check it** - treat as one measurement by one agent, and re-sample before relying on it for a concurrency decision. Memory is not the concurrency limit; one provider account
  and one Unity are.
- **Worker lifetime 3600s vs a single role's 3600s** — a repair cycle cannot finish on the stock profile. Use
  `worker-claude-sonnet-long.json` (10800s); it is a config value, not code.
- **Graph, 2026-09-17**: 75 active implementation tasks, 58 remaining, 15 dispatchable, 8 concurrently runnable,
  36 blocked, **17 of 95 conformant**, and **102 of 119 blocking links point at `not_delivered`**. The constraint is
  evidence, not code.
- **Contention**: `Assets/Scenes/DoorPrototype.unity` ~31 claims, `DoorPrototypeSceneBuilder.cs` ~27. Harmless while
  most claimants are blocked. That scene is also the only one committed **binary** while the project is ForceText.
- **PixelLab meter**: 132 metered against 97 printed on the wizard run, ratio 1.36. A per-run measurement, not a
  rate — a later batch measured 70 against 70.5.
