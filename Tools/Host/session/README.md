# Session tools: replacing an agent session

`nsc_session_digest.py` turns an old Claude desktop session's transcript into a digest that a new session can read. Use it to:
- recreate the standing agents after switching Claude accounts;
- replace an agent whose context is too full.

Written 2026-09-17 by the "Agent transfer between accounts" session, at Vincent's request. The tool is read-only: it never changes transcripts or app data.

## What survives an account switch (checked 2026-09-17)

- **Transcripts stay.** Every session under this Windows user writes `C:\Users\VincentLiguori\.claude\projects\C--NSC\<cli session id>.jsonl`, whichever Claude account ran it. Both accounts' transcripts were in that one folder.
- **The sidebar doesn't.** The app keeps each account's session list in its own folder: `claude-code-sessions\<account>\<org>\local_<id>.json` under `%APPDATA%\Claude`, which the Store app redirects to `%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude`. Each record maps a sidebar title to its transcript (`cliSessionId`).
- **Memory, the docs, the board and the journal stay.** They are ordinary files.
- **No agent can create a session.** Vincent clicks + for each one, and the new session renames itself.
- **`list_sessions`, `list_events` and `send_message` only reach the account signed in now.** An old account's sessions can be read only from disk, with this tool.
- **Transcripts are 1-90 MB.** Never open one directly. A digest is about 12-31K tokens.
- Claude Code can delete old transcripts after its retention period (`cleanupPeriodDays`, 30 days by default; not set here). Build digests soon after a switch. Digests are kept.

## Commands

```text
python -B C:\nscrev\session-tools\nsc_session_digest.py list [--archived]
python -B C:\nscrev\session-tools\nsc_session_digest.py digest --title "Game Agent"
python -B C:\nscrev\session-tools\nsc_session_digest.py digest --session <local_... id or cli session id>
```

- `list` shows the sessions of every account on this machine. `*` marks the account signed in now.
- `digest --title` picks the most recent other session with that title, or "<title> (retired ...)". It never picks the session running the command. It writes `C:\nscrev\reports\agent-recovery\<title>-<yyyymmdd-hhmm>-<cli8>.md`.
- Digest sections:
  - Source, including other sessions with the same title and earlier digests of it;
  - 1: the launch prompt;
  - 2: Vincent's later messages, including ones typed while the session was busy;
  - 3: messages from other sessions;
  - 4: the latest compaction summary;
  - 5: the latest replies;
  - 6: files written, git writes, messages sent, subagents and artifacts.
- Sections 2, 3 and 5 keep the newest items that fit their budget. `--scale 0.5` halves every budget.

## Replace one agent without creating a session (preferred, 2026-09-18)

**A session can clear itself.** `mcp__ccd_session_mgmt__clear_session` with `session_id: "self"` empties the transcript when the turn ends,
while the session keeps its folder, model, permissions, settings and **title**. The old conversation stays recoverable through "Resume previous
session", and the transcript remains on disk for a digest.

**Why prefer it over creating a new session:**
- **Other agents keep messaging the same session id.** A new session changes the address every other agent has saved.
- **Vincent does nothing in the sidebar.** The Retire/Successor procedure below makes him create a session for no reason.
- **It is recoverable.** If the handoff turns out to be missing something, resume the old conversation and write it down.

**Steps:**
1. Do everything in the **Retire** prompt below: safe point, journal checkpoint, handoff file, memory. The handoff matters more here than in the
   two-session flow, because **`nsc_session_digest.py` will not digest the session running it** - a self-clear has no digest to lean on.
1a. **Digest your own transcript before writing the handoff** — do not write it from memory alone:

    ```text
    python -B C:\nscrev\session-tools\nsc_session_digest.py digest --session <your cli session id>
    ```

    The id is the `.jsonl` filename under `C:\Users\VincentLiguori\.claude\projects\C--NSC\`. **Read section 2, Vincent's
    messages, oldest first.** A long session has been compacted more than once, so its earliest instructions are no longer in
    its context at all: on 2026-09-18 a digest of 175 messages across 3 compactions surfaced four ideas Vincent had raised and
    nobody had closed, none of which the session could remember. **An author cannot write down what it has forgotten.**

2. Say what needs saying in the same turn, then call `clear_session` with `"self"`. The app asks Vincent to approve it.
3. Vincent pastes one line to wake the cleared session:

```text
You are the <TITLE>. Read C:\NSC\nsc-handoff-<yyyymmdd>-<title>.md and C:\NSC\nsc-fleet-state.md, then continue.
```

`CLAUDE.md` and the memory index load automatically; the agent directory and role guides supply the rest.

**When the two-session flow below is still right:** switching Claude accounts (the sidebar does not follow the account), or when you want the old
session left intact and readable beside the new one.

**A caveat worth stating plainly:** nothing from the cleared conversation carries over. Anything known but never written to a file, a memory, the
board or a guide is gone. Externalise as you work rather than at the end - the handoff should be the small remainder, not the whole record.

## Replace one agent (context too full)

1. Paste **Retire** into the old session and wait for the handoff file path.
2. Create a new session in `C:\NSC` with the same model and effort, and paste **Successor** with the title filled in.
3. The successor renames the old session "<title> (retired <date>)" and takes the title. Archive the old session whenever you like.

## Recreate the agents after switching accounts

1. If the old account still has quota, first paste **Retire** into each agent.
2. On the new account, create one session in `C:\NSC` (Sonnet 5 is enough) and paste **Recovery**.
3. For each agent it lists, create a session with the model and effort it shows, and paste the prompt it gives you.

## Retire

```text
I'm replacing this session with a fresh one, because your context is full or I'm switching Claude accounts. Don't start anything new.

1. Bring running work to a safe point, or record exactly where it stands. Don't kill running jobs; record their IDs and logs.
2. Write a journal checkpoint and a handoff file, following C:\NSC\nsc-checkpoint-handoff-guide.md sections 2 and 3. Name the file C:\NSC\nsc-handoff-<yyyymmdd>-<your title in lowercase with dashes>.md, for example nsc-handoff-20260917-game-agent.md.
3. In the handoff file, put what your guides and memory don't already say: my standing instructions to you, decisions waiting on me, open handoffs with their BOARD.md row IDs, in-flight IDs and log paths, and anything your successor must not touch.
4. Save durable facts to memory, in the third person and naming your agent. Mark stale memories as historical.
5. Reply with only the handoff file path. Then stop.
```

## Successor

Replace `<TITLE>` on the first line only.

```text
Your title: <TITLE>

You are the No Safe Circle agent with that title, starting in a new session. You replace an earlier session with the same title: its context filled up, or it stayed behind on another Claude account. Continue its work without redoing or undoing anything.

Set up:
1. Load mcp__ccd_session_mgmt__get_session, mcp__ccd_session_mgmt__list_sessions and mcp__ccd_session_mgmt__set_session_title with ToolSearch. If list_sessions shows another session with your title, rename it to "<your title> (retired <yyyy-mm-dd>)". Then rename "self" to exactly your title, and confirm it with get_session.
2. Build your predecessor's digest. Never open a .jsonl transcript directly; they are 1-90 MB.
   python -B C:\nscrev\session-tools\nsc_session_digest.py digest --title "<your title>"

Read, in order:
3. C:\NSC\nsc-agent-directory.md. Your row in section 2 gives your role, guides and lane. Read those guides and any agent file they name.
4. The newest C:\NSC\nsc-handoff-*.md for your title or role, if one exists.
5. The digest:
   - section 1 is how your predecessor was launched;
   - section 2 is my instructions since then, and newer ones win;
   - sections 3-5 show where the work stood;
   - section 6 lists its files, git writes, handoffs and subagents.
   If your predecessor ran for less than a day and the Source section lists an earlier digest, also read that digest's sections 2 and 4.
6. The rows in C:\nscrev\reports\handoffs\BOARD.md from or to your title, and your role's newest entries in C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\graph-lead-journal.md.

Then:
7. Verify, don't trust (C:\NSC\nsc-checkpoint-handoff-guide.md, section 5). A job with no process, container or result is unknown, not failed. Rerun nothing whose result may exist.
8. Approvals in the digest covered your predecessor's exact actions at the time. Ask me again for anything that needs my go.
9. Append a short "resumed" entry to the journal: what you verified, and what differed from the digest.
10. Send one line by title to each running agent you have open handoffs with: "<your title> restarted in a new session; same lane, same open handoffs."
11. Confirm your title again with get_session. Reply to me in at most 3 lines: what you're resuming, what differed, and what you need from me. Then carry on in your lane.
```

## Recovery

```text
You are the Agent Recovery session for No Safe Circle. I switched Claude accounts, so my standing agent sessions from the other account are gone from the sidebar, but their transcripts are still on disk. Tell me exactly which agents to recreate. Don't do any agent's work, and don't read transcripts or digests.

1. Run: python -B C:\nscrev\session-tools\nsc_session_digest.py list
   Rows marked * belong to the account signed in now.
2. The standing agents are the titles under "Running as sessions" in section 2 of C:\NSC\nsc-agent-directory.md, plus any live row whose title ends in "Agent". Keep the ones with no row marked * yet.
3. If a title has no transcript, or live rows from two old sessions share it, tell me instead of guessing.
4. Reply with a table: title, model / effort / mode, last activity. Then, for each agent, give me the complete Successor prompt from C:\nscrev\session-tools\README.md with its title filled in, ready to paste. I'll create each session in C:\NSC with that model and effort.
```
