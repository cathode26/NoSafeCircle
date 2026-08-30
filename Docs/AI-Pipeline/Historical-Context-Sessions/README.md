# Historical Context Sessions

This directory preserves human/agent working history for the No Safe Circle AI pipeline without turning old conversations into repository authority.

## Read order for a new agent

1. Read `CURRENT_CONTEXT.md`.
2. Verify every dynamic fact it names against the current repository, TaskGraph, and GitHub workflow state.
3. Read only the session handoff(s) referenced by `CURRENT_CONTEXT.md` when additional rationale is needed.
4. Read `raw/` transcripts only when a concise handoff does not answer a historical question.

The normal continuation path should therefore be:

`CURRENT_CONTEXT.md` -> deterministic verification -> one focused session handoff -> raw transcript only if necessary.

## Authority and precedence

Historical context explains **why**. Current deterministic project state proves **what is true now**.

When sources disagree, prefer them in approximately this order:

1. Current Git objects, branch/commit identity, and working-tree state.
2. Current TaskGraph contracts, evidence, validation, and committed configuration.
3. Current validated GitHub Issue workflow state, event chain, PR state, and remote refs.
4. Current tests and deterministic validation artifacts.
5. `CURRENT_CONTEXT.md`, after its dynamic facts are re-verified.
6. Structured historical session handoffs.
7. Raw chat/session transcripts.

Never change current repository state merely to make it agree with historical context.

## What belongs here

A substantial work session should leave two possible records:

- **Structured handoff** — concise working memory: objective, decisions, exact starting/ending identities, validation, unresolved work, and next action.
- **Raw transcript** — optional immutable archaeology when the full conversation is worth retaining.

Do not use one continuously appended transcript. Create immutable snapshots.

Recommended names:

```text
YYYY-MM-DD-short-session-slug.md
raw/imported-YYYY-MM-DD-source-name.txt
```

## CURRENT_CONTEXT.md rules

`CURRENT_CONTEXT.md` is the only intentionally mutable file in this directory.

Keep it short enough that a new ChatGPT, Claude, or Codex instance can read it immediately. It should contain:

- current objective;
- canonical repository/checkouts;
- current stage/workstream;
- last session-reported branch/SHA/Issue/PR state;
- architectural invariants;
- known operational hazards;
- exact next action;
- links to the one or two handoffs that explain the current work.

Dynamic values such as `HEAD`, `origin/main`, Issue state, PR head, or working-tree cleanliness are **not authoritative merely because this file says so**. A new agent must verify them before mutating anything.

## Structured handoff rules

Once committed, a historical handoff should normally be immutable. If a later session changes the project state, create a new handoff and update `CURRENT_CONTEXT.md`; do not rewrite the old record to make history look current.

Every handoff should explicitly distinguish:

- **Starting state**
- **Decisions made**
- **Work performed**
- **Validation/evidence**
- **Ending state**
- **Unresolved issues**
- **Next action**

Use `SESSION_HANDOFF_TEMPLATE.md`.

## Raw transcript rules

Raw transcripts are advisory historical records only.

Before committing a raw transcript, check for:

- API keys, tokens, cookies, passwords, or authentication material;
- personal or unrelated conversations;
- private filesystem or account data that does not belong in the project;
- enormous generated logs already preserved elsewhere;
- duplicated output that adds no historical value.

Do not rewrite old raw logs merely to replace historical paths with current paths. A historical path is evidence of what was true at that time.

The imported raw files in this bootstrap were scanned for common OpenAI/GitHub/AWS private-token patterns; no matching credential values were detected. Mentions of environment-variable names and authentication commands remain because they are part of the technical history. See `raw/MANIFEST.md`.

## What should NOT happen

Do not let this directory become another authority/state machine.

It should not:

- select tasks;
- acquire claims;
- modify Issues;
- drive merges;
- supersede TaskGraph;
- infer current state from old transcripts;
- require an LLM to reconstruct the entire project every session.

The directory exists to make human/agent continuation cheaper and safer.

## Agent entry-point snippet

The following can be added near the top of `AGENTS.md` and `CLAUDE.md`:

```markdown
## Project continuation context

For ongoing Task Orchestrator / TaskReviewAgent work, read:

Docs/AI-Pipeline/Historical-Context-Sessions/CURRENT_CONTEXT.md

Verify its dynamic Git, TaskGraph, GitHub Issue, remote-ref, and PR facts against
the current repository before taking a mutating action.

Read referenced historical handoffs only when rationale is needed. Raw session
transcripts are advisory history, not repository authority.

If historical context disagrees with current deterministic project state, the
current deterministic project state wins.
```

## End-of-session habit

At the end of a substantial session:

1. Verify Git/TaskGraph/GitHub facts.
2. Write one structured handoff using the template.
3. Update `CURRENT_CONTEXT.md` to point at that handoff.
4. Optionally add an immutable raw transcript after a secret/privacy review.
5. Commit the context update with the code/workflow state it describes when practical.

This is working memory plus historical memory, not a replacement for Git.
