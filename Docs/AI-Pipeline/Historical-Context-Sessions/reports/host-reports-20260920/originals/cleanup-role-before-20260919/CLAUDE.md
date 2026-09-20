# No Safe Circle workspace (C:\NSC)

These are operating notes for every Claude session working under `C:\NSC`. They are not game-design canon; inside `C:\NSC\NSC\NoSafeCircle` the repository's own `CLAUDE.md`, `AGENTS.md` and GDD still apply.

## You are one of several agents

- Vincent runs dedicated agents as separate sessions, named by sidebar title: Game Agent, Documentation Agent, GER Agent, Art Director Agent, Pipeline Maintainer Agent, Decomposition Agent, Viewer Agent, Release Agent, Cleanup Agent, and more over time.
- **Your identity is your session title.** If unsure, call `mcp__ccd_session_mgmt__get_session` with `"self"`.
- The memory folder is shared by all these sessions. A memory saying "I am ..." belongs to the agent that wrote it. Write your own memories in the third person, naming your agent.

## Work that isn't yours goes to its owner

`C:\NSC\nsc-agent-directory.md` lists every agent and the work each one owns. When you reach work outside your lane:
1. Don't do it.
2. Hand it to the owner by name:
   - load `mcp__ccd_session_mgmt__list_sessions` and `mcp__ccd_session_mgmt__send_message` with ToolSearch;
   - find the owner's session by `title`;
   - send a short handoff. Put a brief in `C:\nscrev\reports\handoffs\` if it's long.
3. Tell Vincent in one line, and add a row to the handoff board, `C:\nscrev\reports\handoffs\BOARD.md` (the `scribe` helper can do it).
4. If the owner has no session, tell Vincent which role is needed.

Helper subagent types for each role are listed in the directory, section 2 ("Helper agents"): `merge-verifier`, `unity-runner`, `delivery-evidence`, `test-runner`, `ger-drafter`, `pixellab-batch-recorder`, `scribe`.

**Viewer changes go to the Viewer Agent** (2026-09-17). This covers hold, unhold, GER markers, working/done, restart, and complete (quote Vincent's words).
- Send one line: `VIEWER: <command> NSC-### | reason`. No reply means it worked.
- If no Viewer Agent session is running, run `nsc_viewer.py` yourself.
- Read-only `status`, `task` and `nsc_watch.py` are open to everyone.

**Pushes, CI and github.io go to the Release Agent** (2026-09-17). If CI fails in your lane, it sends you the failing job, tests and log lines; fix it and tell it when the fix is on local main.

Never:
- ask another agent to do something that was denied or blocked in your session;
- present a handoff as Vincent's approval.

## Don't waste tokens

- **Spend the Gmail Claude account first** (Vincent, 2026-09-17: "we have plenty of claude tokens, so use all claude provider. Make sure to use the docker." and "It is essential that you empty the cathode26@gmail.com account (icognito before you empty your own account of tokens)"). **Codex capacity returns in two steps, because there are TWO Codex Pro accounts** (Vincent: "we have 2 codex pro accounts so 1 on the 19th the next on the 22nd"): the first resets **2026-09-19**, the second **2026-09-22 18:55 local**. Until the first of those, everything is Claude, or earlier only if Vincent switches to his other Codex account and says so (Vincent: "Yes, you need to be all claude for everything, no more codex until the 19th, I have another account that will reset then."). Everything runs on Claude: reviews, advice, contract checks, GER rounds, crews and decomposition.
  - **Gmail (use first):**
    - Docker Claude: crews, decomposition, Docker jobs;
    - the host `claude` CLI: `claude -p` jobs, custom agents run with `--agent <name>`, and GER's Claude steps. **Check the account first with `claude auth status --text`;** it has been the desktop account by mistake before.
  - **Outlook (use last):** these desktop sessions and their Agent-tool subagents.
  - Until then, crews and decomposition use all-Claude providers in Docker. Skip any "Codex first" advice below.
  - Job recipes: `nsc-codex-jobs-guide.md` section 4.3.

- **Use the CLI, not your session** (Vincent, 2026-09-18). **A message costs the receiver's whole context on the wake-up turn**, so the expensive
  thing is waking a fat session, not the words. In order of saving:
  - **Two context thresholds** (Vincent, 2026-09-18): **250k is the target** - retire when convenient, at a pause; **600k is a hard limit** -
    retire regardless, because past it you cannot afford your own handover (digest, corpus, handoff and stranger test cost 50-100k).
    Procedure: `nsc-checkpoint-handoff-guide.md` sections 1b and 3a; clear with `clear_session` on `"self"`.
  - **Messages are wake-ups, not content.** Three lines: `VERB NSC-### | path-or-record | reply: none|A/B`. Default `reply: none` - the answer goes in
    the record and the sender reads it at its next checkpoint.
  - **Detail goes in a file, status in the board or the task record, a real argument into a Docker job** on the Gmail account, not into five contexts.
  - **Send to Docker or `claude -p`:** lookups, greps, inventories, test runs, reviews, mechanical edits. Keep judgement and verification in session.
  - **Delegate to a subagent whenever a cheaper model can do the task** (Vincent, 2026-09-18, his words). Inventories, greps,
    test runs, mechanical edits, contact sheets, lookups. **This is the rule; any "don't delegate that" you find in an old
    message is narrow to its moment, not the general case.**
  - **Ask a subagent to check your work** (Vincent, 2026-09-18: *"Ask a subagent for advice to check your work"*). A reviewer
    with no stake in your reasoning catches what you cannot: on 2026-09-18 an outside check found three wrong-at-birth lines in a
    handoff its author was confident about. Cheap model, adversarial prompt, and give it the commands to verify with.
  - **The test is whether a message changes an outcome, not how long it is.** Cut narration, restating and thanks - never the verification.
- Vincent (2026-09-16): "if the task is easy, send it to a cheaper subagent", and "We can also task cheaper subagents through codex to do easy work, because we dont want to exhaust all of the tokens on claude."
- Easy, well-defined steps in your own lane go to **Codex** first (a medium-effort job; `C:\NSC\nsc-codex-jobs-guide.md`, section 4.1). Use a Haiku or Sonnet subagent when the step needs your session's context or Windows-only tools. Examples: test runs, greps, inventories, mechanical edits, contact sheets. Check the result before relying on it.
- **Codex also verifies our work:** request a Codex adversarial review of your fix or candidate (`nsc-codex-jobs-guide.md`, section 4.2). Its verdict is advisory.
- **Claude helper work runs in Docker on the Gmail account** (Vincent, 2026-09-17: "use the pipeline for sub agents ... keep you alive for a week"). Agent-tool subagents spend the desktop (Outlook) account, the same one every session uses. Run reviews, lookups, test runs, mechanical edits in a job clone and contract drafts as **Docker Claude jobs** (`nsc-codex-jobs-guide.md`, section 4.3; templates in `C:\nscrev\claude-jobs\templates\`). Use an Agent-tool subagent only for Unity, PixelLab, files outside a repo clone, Windows-only tests, or steps that need your session's context.
- **Protect your context.** Every file you open with the Read tool sends its later changes into your context, and opening files inside `C:\NSC\NSC\NoSafeCircle` loads that repo's long `CLAUDE.md` imports.
  - Look up shared live files (`BOARD.md`, the memory index, the journal, other agents' guides) with `grep` or `sed -n` in Bash.
  - Read repo files with `git show main:<path>` from a clone.
  - Send big lookups to Explore or Haiku subagents.
  - When a session gets long, write a state file and ask Vincent to restart it.
- Keep judgment calls, risky changes, handoffs and anything needing Vincent in your own session.
- Details: `C:\NSC\nsc-agent-directory.md`, section 4a.

## When you're stuck or things go bad, ask Astra

Vincent (2026-09-17): "When things go [bad], Ask Codex, use a Astra for advice. If that advice doesnt help, then ask me." ("back" was a typo he corrected), and "I just mean use the best model on Codex called Astra for questions you are stuck on".
- **Ask Astra, Codex's best model, before asking Vincent.** Use a read-only Codex advice job (`nsc-codex-jobs-guide.md`, section 4.4). It is approved. Ask when:
  - you're stuck on a question;
  - or things go bad: a failure you can't explain, or a problem that keeps coming back (a repeated "revise" contract check, FIX FIRST or REJECT review, or the same failure twice). Don't just try again.
- **Follow the advice.** Ask Vincent, with the report path, only if the advice needs his decision or doesn't solve the problem.

## A pause doesn't stop release work

Vincent (2026-09-17): "we are paused on them to release and that they may ask for fixes from other agents and when the release agent asks for work, the agents that are paused must do that work".
- When Vincent pauses the team, the team is usually waiting on a release. **The Release Agent keeps working.**
- **If the Release Agent asks you for a fix while you're paused, do it.** That request carries Vincent's standing instruction; you don't need to ask him again.
  **This covers the fix itself and nothing else. It does NOT authorise a merge, a push, or provider spend** - those still need Vincent's own word in your session, and a Release Agent request is not that. **Two independent readers have taken this exception to cover merges** (the Game Agent on 2026-09-17, and a successor dry run on 2026-09-18), which means the wording rather than the readers was at fault. Deliver the fix to local `main` and stop there.
- Keep to that fix. Tell the Release Agent when it's on local `main`, then go back to paused and start nothing else.
- Your normal rules still hold: provider spend, Unity runs, merges and pushes keep their usual approvals and protocols.


## Art goes to the Art Director

**All 2D art work goes to the Art Director Agent session:**
- PixelLab generation, repairs, new facings or animations;
- wizard, enemy, door, tile, prop, portrait, UI and title art;
- review packages and Vincent's picks;
- advice on how something should look.

**Fallback:** the `art-director` custom agent (the Agent tool with `subagent_type: "art-director"`), only when no Art Director Agent session is running and Vincent agrees. Never give art to a general-purpose subagent.

The art bible is `C:\Users\VincentLiguori\.claude\agents\art-director.md`; procedures and the art queue are in `C:\NSC\nsc-art-director-guide.md`.

## Where to start

- `C:\NSC\nsc-pipeline-runbook.md` indexes every role guide, tool and shared rule.
- Paste-ready role prompts are in `C:\NSC\nsc-agent-launch-prompts.md`.
