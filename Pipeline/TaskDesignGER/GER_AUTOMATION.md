# Task Design GER automation: how the GER owner runs it today

This document describes the operator tooling the GER owner (Claude) uses to run the
[GER agent runbook](GER_AGENT_RUNBOOK.md) end to end for the held-task queue. The
runbook remains the process authority. This page records the concrete mechanics:
commands, evidence layout, checks, and lessons learned.

**Status (2026-09-14):** the round runner, node driver and contract-apply tools
listed below live outside the repository in `C:\nscrev\ger-tools\`. They are
operator tooling, not yet reviewed repository code. Porting them into
`Pipeline/TaskDesignGER/` with smoke tests is a recommended follow-up.

## 1. Flow at a glance

For one held task, the GER owner runs these steps in order:

1. **Confirm hold.** The task ID is listed in the journal's GER-holds section and in
   `held-task-ids.json`.
2. **Prepare packet.** Run `task_content_ger.py` on committed main, adding Vincent's
   current decisions with `--feedback-file`.
3. **Freeze source.** Take a blob-exact snapshot of the packet's source commit, shared
   by every task prepared at that commit.
4. **Start marker.** The live viewer marker turns the node brown (**GER in progress**).
5. **Run four rounds.** Codex Generate, a fresh Claude Evaluate, one bounded Codex
   Refine, and a fresh Claude re-audit. Each round writes one immutable directory.
6. **Decide.** Act on the re-audit's final recommendation:
   - `commit_contract` or `commit_contract_then_decompose`: apply and commit the audited
     contract (section 6).
   - `needs_design`: batch the exact questions for Vincent, record his answers, then run
     a fresh cycle.
   - `blocked_not_design`: pause the marker and report the blocker.
7. **Release.** Remove the journal hold and run the marker `finish` step, or run D1B.2
   first when the task is too large for one worker.

The GER owner runs about five tasks at once. Contract commits to main are made one at a time.

## 2. Packet and snapshot

**Packet.** From `C:\NSC\NSC\NoSafeCircle`:

```powershell
python -B Pipeline\TaskDesignGER\task_content_ger.py NSC-044 --output-dir C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\RoomContentGER\<yyyyMMdd-HHmmss>-NSC-044 --feedback-file <decisions.txt>
```

- **Clean sources:** the paths that feed a packet must have no uncommitted changes:
  `Tasks`, `Docs`, `Pipeline/GDDRAG`, `Pipeline/TaskDesignGER`, `Pipeline/TaskGraph`, and the
  art folders. Unrelated uncommitted work elsewhere on main is recorded, not included.
  Unity is usually open on this checkout and can modify plugin files or `ProjectSettings`.
- **Feedback file:** it carries Vincent's standing decisions into the packet, where they
  are hashed.

**Snapshot.** Built with
`git -c core.autocrlf=false -C C:\NSC\NSC\NoSafeCircle archive <source_head> AGENTS.md Tasks Docs Pipeline/TaskGraph Assets/NoSafeCircle Assets/Scenes ProjectSettings Packages`.

- **Location:** extracted to `...\RoomContentGER\_snapshots\<sha12>-blob`, with a
  `<sha12>-blob.SNAPSHOT_IDENTITY.json` beside it.
- **Why a snapshot:** providers read this frozen copy, never the live checkout. That keeps
  a round stable while Primary Sol commits, and avoids Claude Code's workspace-trust
  refusal in the repository.
- **Why `core.autocrlf=false`:** a plain `git archive` on Windows converts text files to
  CRLF.
- **Concurrency:** one snapshot per commit, created under a lock file.

## 3. Provider rounds (`ger_round.py`)

```text
python -B C:\nscrev\ger-tools\ger_round.py --packet <packet-dir> --snapshot <snapshot-dir> --round 01-codex-generate|02-claude-evaluate|03-codex-refine|04-claude-reaudit
```

**Before every round:**
- The snapshot must match the packet's `SOURCE_IDENTITY.json`.
- The selected task, GDD and art direction on current main must still match the packet;
  any change is drift, so the round fails closed and a fresh packet is needed.
- Both comparisons ignore CRLF/LF differences only (see section 8).

**Codex rounds (01, 03).** `codex exec` runs with these flags:
- `--json` and `--output-last-message <round>/OUTPUT.md`;
- `--sandbox read-only`, `--cd <snapshot>` and `--skip-git-repo-check`;
- `-c model_reasoning_effort="high"`, set by Vincent. The user default is `xhigh`, which
  roughly doubles round time.
- one `--image` per reference image, all of R01 to R17.

The prompt is sent on stdin. A round takes about 13 minutes at `high` and uses about
2-4 million tokens, mostly cached.

**Claude rounds (02, 04).** `claude -p` runs with these flags:
- `--output-format json` and `--add-dir=<snapshot>`;
- `--allowedTools=Read,Grep,Glob`;
- `--disallowedTools=Bash,Edit,Write,NotebookEdit,WebFetch,WebSearch,Task`.

It runs with the round directory, outside the repository, as the working directory. The
prompt is sent on stdin. Each Claude round is a new conversation.

**Every prompt states:**
- the read-only boundary and the required reading: the Unity programmer language,
  game-task lessons and the Unity testing policy;
- the ownership context in `Tasks/`, and the review dimensions:
  - theme, content and visual composition;
  - gameplay mechanics;
  - missing specification;
  - file ownership and dependencies;
  - meaningful tests, which must exercise the production path;
  - asset availability and contract quality;
- the room size authority, all 17 references with their README descriptions, and
  existing art paths;
- "think like the wizard player" questions: cover and line of sight, Fireball charge room,
  Frost Field lanes, Force Wave space, escape loops and holding a door;
- Vincent's standing decisions, including catalog-row ownership, near-wall cutaway,
  per-room wall Tilemaps, player start, and "choose room size on design merit".

**Each round directory holds:**
- `PROMPT.md`, the prompt sent;
- the raw provider stdout: `RAW_EVENTS.jsonl` for Codex, `RAW_RESPONSE.json` for Claude;
- `STDERR.log` and `OUTPUT.md`;
- `METADATA.json`: provider, CLI version, model, session ID, timestamps, exit code,
  source checks, input and output SHA-256s, and the exact command.

A round fails closed with `FAILED.json` on a non-zero exit, a provider error, empty
output, a missing session ID, a timeout (the process tree is killed), or source drift.
Round directories are never reused. A superseded partial round keeps
`ABORTED_BY_OWNER.json` explaining why.

## 4. Node driver (`ger_node.py`)

```text
python -B C:\nscrev\ger-tools\ger_node.py NSC-045 --feedback-file <decisions.txt> --timeout 3600
python -B C:\nscrev\ger-tools\ger_node.py NSC-044 --existing-packet <packet-dir>
```

The driver runs the whole cycle for one task:
1. Confirms the hold.
2. Prepares the packet, or reuses an existing one.
3. Ensures the snapshot exists.
4. Starts the marker.
5. Runs the missing rounds in order, stopping at the first failure.

It writes `NODE_STATUS.json`, including the parsed re-audit recommendation. On failure
it pauses the marker, which turns the node gray and keeps the hold. Logs are in
`...\RoomContentGER\_logs\<ID>.node.<version>.log`.

## 5. Monitoring

- **Round status:** each round directory is running (no `METADATA.json` yet), done, or
  failed (`FAILED.json`).
- **Codex progress:** read `%USERPROFILE%\.codex\state_5.sqlite` (table `threads`, where
  `cwd` is the snapshot) and `thread_history_1.sqlite` (table `thread_items`: agentMessage,
  commandExecution) in read-only mode. The rollout `.jsonl` files are not used by this
  Codex version. Low local CPU is normal while the model reasons on the server.
- **Viewer:** port 8828 answers on `http://localhost:8828/api/state`. Each task row carries
  `ger_overlay` and `held_overlay`. A page loaded before a marker change keeps its old
  colors until reloaded.

## 6. Contract commit (`apply_contract.py`)

```text
python -B C:\nscrev\ger-tools\apply_contract.py --packet <packet-dir>                    # dry run
python -B C:\nscrev\ger-tools\apply_contract.py --packet <packet-dir> [--override-json <fields.json>] --commit
```

**Preconditions:**
- all four rounds succeeded, and the re-audit recommends committing;
- `Tasks/<ID>.yaml` at HEAD and in the working tree still matches the packet;
- the round-03 final contract keeps `id`, `parent`, `schema_version` and
  `reconciliation_key`, and increments `contract_revision` by exactly one.

**Effects:**
- **Task file:** rewrites only `Tasks/<ID>.yaml`, keeping the existing key order and the
  file's own CRLF or LF. `--override-json` applies the re-auditor's quoted minor edits.
  A `provenance.task_design_ger` record is added.
- **Resource groups:** keeps `RESOURCE_GROUPS.yaml` in step. A resource claimed by more
  than one task must have a group whose members exactly match the claimants
  (`work_graph_validate.py`). The tool mirrors `graph_delta.py` `_update_resource_groups`
  and applies only the changed or created groups.
- **Validation:** runs `Pipeline/TaskGraph/taskcontrol.py validate` and restores the files
  on failure.
- **Commit:** refuses if anything is already staged. Stages exactly the changed paths and
  commits with `No Safe Circle Task Design GER <task-design-ger@nosafecircle.invalid>`.
  Never pushes.

After a commit, record it in the journal's GER queue status and release the task with the
marker `finish` step, or run D1B.2 first.

## 7. Design decisions and source edits

**Where decisions go.** When Vincent answers a `needs_design` question, record it in
three places:
1. the journal;
2. the canonical source it governs, which is one of:
   - the GDD, then run `python Pipeline/GDDRAG/gddctl.py rebuild`, `validate`, and the
     three GDDRAG tests, and commit the knowledge base with the GDD;
   - the art direction;
   - the affected task contracts;
3. the feedback file for the next packets.

**When to edit.** Commit source changes only when no running round depends on those
files, because a running round treats them as drift.

**Decisions recorded on 2026-09-14:**

| Decision | Where it is recorded |
|---|---|
| Room size is a maximum of three times each side, and clearances stay minimums | GDD section 13 |
| Room tasks own their `RoomSceneCatalog` row | NSC-069 AC-006 |
| NSC-049 composes at catalog bounds and places the Player at NSC-044's start point | NSC-049 AC-001 and AC-003 |
| The camera follows the wizard, near walls use a low cutaway stub, and each room owns its wall Tilemap | Dungeon art direction |

## 8. Lessons learned

- **Why v2 rooms did not grow.** The resize was blocked by room-catalog ownership (the
  catalog belonged to NSC-069 only) and by a prompt that asked for one whole-room review
  shot. With only one refine, the author retreated to the baseline. Resolve ownership
  before asking GER to change shared data, and tell the rounds explicitly how the camera
  works.
- **Shared resources need a resource group.** Adding one task's claim to a file that
  another task already claims fails `taskcontrol validate` until the group is updated.
- **Git Bash paths.** Pass `C:/NSC/NoSafeCircle-AssistantCheckouts` to the marker tool with
  forward slashes; unquoted backslashes are consumed.
- **CRLF.** `SOURCE_IDENTITY.json` hashes the Windows working copy, so text-file hashes
  can differ from the LF blob bytes in the snapshot.
  - The runner's checks ignore line endings.
  - Every prompt tells providers that a CRLF-only mismatch is not a finding.
  - Vincent chose to leave the preparer unchanged, since this workaround covers it.
- **Unity is live.** It may delete or modify files in the canonical checkout. Stage exact
  paths, and never commit or revert files the GER owner did not change.
- **Stopping a run.** When Vincent changes design authority mid-run, stop the affected
  rounds, preserve them with `ABORTED_BY_OWNER.json`, record the decision, and restart on
  fresh packets.
