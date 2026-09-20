# Brief: fix the Pipeline Maintainer's reviewer method, and record when host CLI beats Docker

**From:** Pipeline Maintainer Agent. **To:** Documentation Agent. **Date:** 2026-09-18.
**Authority:** Vincent, 2026-09-18, in the Pipeline Maintainer's session: *"Yes have the doc agent
fix the role guide and record when cli beats docker and yes, hand it over."*

He asked after noticing I was reviewing with CLI Fable and wanting to know whether documentation
said which method to prefer. It does, in three places, and they disagree.

## Change 1 — `C:\NSC\nsc-pipeline-maintainer-guide.md`, line 106

**It currently says** (quoted exactly):

> Start a **new** reviewer; don't reuse the author. Call the Agent tool with
> `subagent_type: "pipeline-reviewer"` (Opus 5 at xhigh), adding `model: "fable"` for identity,
> locking or provider-spend code. A Codex reviewer is also acceptable.

**The problem:** the Agent tool spends the **Outlook desktop account**, which `CLAUDE.md:41` lists
as *"use last"*. So my own role guide tells me to default to the account CLAUDE.md says to spend
last. It predates the 2026-09-17 account split and was never updated.

**Suggested replacement** (wording is yours; the facts are the point):

> Start a **new** reviewer; don't reuse the author. Default to the **host `claude` CLI on the
> Gmail account**, which is what the account rule in `CLAUDE.md` wants:
>
>     claude -p --model claude-fable-5-1 --agent pipeline-reviewer --permission-mode bypassPermissions "<prompt>"
>
> Check the account first with `claude auth status --text`; it must say `cathode26@gmail.com`.
> Use a **Docker review job** (`nsc-codex-jobs-guide.md` 4.3) when the review's evidence is
> confined to one job clone. Use the **Agent tool** with `subagent_type: "pipeline-reviewer"` only
> when the review needs Unity, PixelLab, Windows-only tools or this session's own context - it
> spends the scarce desktop account. A Codex reviewer is also acceptable when Codex has quota.

## Change 2 — record when host CLI beats Docker

`CLAUDE.md:64` says to run reviews as Docker Claude jobs, and carves out Agent-tool subagents for
"files outside a repo clone". It says nothing about the host CLI for that case, which is the gap
that made Vincent's question reasonable.

**The fact to record**, wherever you judge it belongs (`nsc-codex-jobs-guide.md` 4.3 seems
natural, with a pointer from the maintainer guide):

> A Docker review job mounts **one job clone**. Reviews whose evidence is spread across the host -
> several clones at once, `C:\nscrev\reports`, `C:\nscrev\job-tools`, a tool that lives outside
> any repo - cannot see it from inside a container, so they run on the host `claude` CLI instead.
> That is still the Gmail account, so it costs nothing extra; only the Agent tool spends Outlook.
> Docker stays the default when the work really is confined to a clone.

**Worked example, if you want one:** the five `propagation_check.py` reviews and the three
`run_job.py` reviews of 2026-09-18 all had to read the tool (in `C:\nscrev\job-tools`, not a
repo), its tests, prior review reports, and `C:\nscrev\ci-134-fix` as a real-repo fixture. No
single job clone contains those.

## What I verified before writing this

- `claude auth status --text` on the host → `cathode26@gmail.com`. Every review today was on Gmail.
- `nsc-codex-jobs-guide.md:290` already lists `pipeline-reviewer` as a valid `--agent` for host
  `claude -p` jobs, so change 1 contradicts nothing in the jobs guide.
- `nsc-codex-jobs-guide.md:264` lists `review-job-prompt.md` with service `claude-exec` for
  "`pipeline-reviewer` and other Claude reviews" - that is the Docker path, and it stays correct
  for clone-confined reviews.

## Not in scope

I am not asking for any change to the account rule itself, only for the role guide to stop
contradicting it and for the host-CLI case to be written down. If you think the right fix is to
change `CLAUDE.md:64` instead, that is a Vincent question, not mine.
