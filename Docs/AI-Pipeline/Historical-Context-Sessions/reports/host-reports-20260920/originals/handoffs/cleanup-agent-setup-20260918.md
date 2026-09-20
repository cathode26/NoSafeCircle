# Cleanup Agent: setup brief (2026-09-18)

**Owner of this file:** Documentation Agent. **Status:** open, waiting on the Pipeline Maintainer's
handover brief.

This file is the durable version of a request that was first sent inline as a message. Vincent,
2026-09-18: *"Remember we should minimize direct communication and we should be communicating
through files"* — so this is the record, and messages about it are three-line pointers here.

---

## 1. The decision, with all three positions dated

| when | his words | effect |
|---|---|---|
| 2026-09-17 | "no That is not your job, we need a clean up agent." (to the Game Agent) | work taken off the Game Agent; role created on paper |
| 2026-09-17 | "Start the Cleanup Agent session :)" | session approved, never created |
| 2026-09-18 evening | "no clean up agent" | role marked NOT STAFFED across the doc set; work unowned |
| **2026-09-18, later the same evening** | **"We need a clean up agent. Please talk to the pipeline maintainer agent about what we found so when you create the agent we have it set up properly. We will need its hand off for it."** | **role reinstated; set it up from tonight's findings; the Pipeline Maintainer's handover is a prerequisite** |

**The newest wins.** All four are kept here rather than overwritten, because a deleted decision comes
back as a fresh idea at the next transcript digest. Board rows: `H-20260918-11` (the decline),
`H-20260917-28` (the Game Agent's original handover).

**The session still does not exist.** Only Vincent creates sessions. What this role owes him is the
exact title and a paste-ready prompt, plus a guide that already contains tonight's findings.

## 2. What happened tonight that the new agent inherits

Done by the Pipeline Maintainer Agent on 2026-09-18, before the role was reinstated:

- **45 directories moved**, all `C:\nsc*` at the drive root, into `C:\NSC-History-20260918`.
  Reversible; nothing deleted. Supporting files in that folder: `MANIFEST.json`, `MANIFEST.md`,
  `MOVE-TO-HISTORY.ps1`, `MOVE-STRAGGLERS.ps1`, `RESTORE.ps1`, `README.md`.
- **Proposed but not run:** quarantining ~788 directories out of `C:\NSC` and ~201 out of
  `C:\nscrev` to the same place. **Held** — it now has an owner who does not exist yet.
- **Review date 2026-10-09**, three weeks after creation, at which anything still in the folder is
  meant to be deletable without an audit.
- **The rule that makes that safe** (Vincent, 2026-09-18, relayed): *"if we go into the history
  folder and find something of value, it needs to come out of the history folder."* The folder is a
  waiting room, never a home. `RESTORE.ps1` moves a folder back and logs it to `RESTORES.md`.

## 3. Open risks the new agent must not inherit silently

1. **`C:\NSC\_worktrees` — 132 entries, not on the guarded list.** Moving a **registered** git
   worktree breaks `git worktree` bookkeeping, and the task records and the viewer point at checkout
   paths; `nsc-task-orchestrator-guide.md` section 4.9 says not to move a worker checkout by hand.
   **This is the one place where "reversible" is weakest:** restoring the directory does not restore
   the registration. It is also where the ~58 GB everyone wants back actually lives, so it cannot
   simply be excluded and forgotten either.
2. **`RESTORES.md` did not exist** when the scheme was announced, while the README says an empty
   `RESTORES.md` is the proof nothing was ever needed. An **absent** file cannot be told apart from
   one never created, so on the review date it proves nothing. It must be created now, empty, with a
   header and the review date.
3. **Authority shape.** The written procedure for this role is a **plan plus a dry-run-by-default
   script that Vincent runs** — not moves the agent makes. 45 directories were already moved before
   the role had an owner. Nothing needs undoing, but the new agent starts from a state that was
   produced outside its own rules, and its guide should say so plainly.

## 4. What the Pipeline Maintainer owes this role

Requested 2026-09-18. Destination: `C:\nscrev\reports\handoffs\cleanup-agent-request-20260918-pipeline-maintainer.md`,
beside the Game Agent's `cleanup-agent-request-20260917.md`, which is the other half of the
inheritance.

- what is already done — the 45 moves, the manifest, the scripts, the review date;
- **the guarded list, exactly, and how it was derived** — including how "dirty, off-main, or recently
  touched" is computed, since the next agent must re-run that judgement and must not invent its own;
- the proposed 788 + 201 pass: how candidates were counted, and whether the scan is depth-1;
- **an explicit answer on `C:\NSC\_worktrees`**;
- confirmation that `RESTORES.md` now exists;
- **what it deliberately did not do, and why** — worth more than the inventory;
- what it would tell the new agent to do first, and what never to touch.

Everything else — the role's lane, authority, what it hands to whom — is the Documentation Agent's
to write.

## 5. What the Documentation Agent does once that brief lands

1. Fold sections 2 and 3 into `C:\NSC\nsc-cleanup-agent-guide.md` (body, below the status line).
2. Write the history-folder rule into the runbook — held until now deliberately, because writing it
   earlier would have ratified the scheme in the doc set before Vincent had ruled on it.
3. Update the roster's Cleanup Agent start prompt so a fresh session inherits all of it, including
   its own `C:\NSC\agent-state\cleanup-agent-todo.md` per runbook rule 20.
4. Give Vincent the exact session title and the paste-ready prompt.

## 6. Reversal already applied to the doc set

The NOT-STAFFED markers added earlier tonight are being removed from the agent directory, the
roster, the runbook, `nsc-fleet-state.md`, the cleanup guide banner and the two memory files, with
the decline kept visible as superseded rather than erased.
