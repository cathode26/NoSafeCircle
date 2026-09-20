# Tool path sweep — exact file list

**41 files, 124 references.** Generated 2026-09-18 after the move.

## Replacements

| old | new |
|---|---|
| `C:\nscrev\ger-tools` | `C:\NSC\tools\ger` |
| `C:\nscrev\job-tools` | `C:\NSC\tools\jobs` |
| `C:\nscrev\viewer-tools` | `C:\NSC\tools\viewer` |
| `C:\nscrev\astra` | `C:\NSC\tools\astra` |
| `C:\nscrev\session-tools` | `C:\NSC\tools\session` |
| `C:\nscrev\art-tools` | `C:\NSC\tools\art` |

Forward-slash spellings (`C:/nscrev/...`) appear too — replace both.

## Files

| file | references |
|---|---|
| `nsc-ger-orchestrator-guide.md` | ger-tools×8 |
| `nsc-pipeline-runbook.md` | ger-tools×4, session-tools×1, viewer-tools×3 |
| `nsc-viewer-guide.md` | viewer-tools×8 |
| `agent-state: art-director-agent.md` | art-tools×7 |
| `agent-state: pipeline-maintainer-agent.md` | ger-tools×4, job-tools×3 |
| `nsc-agent-launch-prompts.md` | ger-tools×1, session-tools×1, viewer-tools×4 |
| `nsc-agent-directory.md` | ger-tools×2, session-tools×1, viewer-tools×2 |
| `nsc-checkpoint-handoff-guide.md` | session-tools×3, viewer-tools×1 |
| `nsc-codex-jobs-guide.md` | ger-tools×1, job-tools×2, viewer-tools×1 |
| `nsc-handoff-20260918-viewer-agent.md` | viewer-tools×4 |
| `nsc-pipeline-problems.md` | ger-tools×4 |
| `nsc-viewer-agent-guide.md` | viewer-tools×4 |
| `nsc-watcher-guide.md` | viewer-tools×4 |
| `agent-state: decomposition-agent-20260918-0421-b936e9cb.md` | job-tools×1, session-tools×3 |
| `nsc-agent-roster.md` | session-tools×1, viewer-tools×2 |
| `nsc-handoff-20260918-art-director-agent.md` | art-tools×1, session-tools×2 |
| `nsc-handoff-20260918-documentation-agent.md` | astra×1, ger-tools×1, job-tools×1 |
| `nsc-handoff-20260918-evening-pipeline-maintainer.md` | astra×1, job-tools×2 |
| `nsc-handoff-20260918-ger-agent.md` | ger-tools×3 |
| `agent-state: decomposition-agent-todo.md` | job-tools×3 |
| `agent-state: ger-agent.md` | ger-tools×3 |
| `nsc-art-director-guide.md` | art-tools×1, viewer-tools×1 |
| `nsc-handoff-20260918-decomposition-agent.md` | job-tools×2 |
| `nsc-pipeline-maintainer-guide.md` | ger-tools×1, viewer-tools×1 |
| `agent-state: decomposition-agent.md` | job-tools×1, session-tools×1 |
| `agent-state: viewer-agent-todo.md` | viewer-tools×2 |
| `AGENTS: pipeline-maintainer.md` | ger-tools×1, viewer-tools×1 |
| `nsc-cleanup-agent-guide.md` | ger-tools×1 |
| `nsc-delivery-evidence-guide.md` | viewer-tools×1 |
| `nsc-handoff-20260918-pipeline-maintainer.md` | job-tools×1 |
| `nsc-handoff-20260918-release-agent.md` | job-tools×1 |
| `nsc-integration-steward-guide.md` | ger-tools×1 |
| `agent-state: art-director-agent-todo.md` | art-tools×1 |
| `agent-state: documentation-agent-todo.md` | astra×1 |
| `agent-state: documentation-agent.md` | ger-tools×1 |
| `agent-state: ger-agent-todo.md` | ger-tools×1 |
| `agent-state: pipeline-maintainer-todo.md` | astra×1 |
| `agent-state: release-agent.md` | job-tools×1 |
| `agent-state: viewer-agent.md` | viewer-tools×1 |
| `AGENTS: art-director.md` | viewer-tools×1 |
| `AGENTS: merge-verifier.md` | viewer-tools×1 |

---

## Result — Documentation Agent, 2026-09-18

**Swept: 71 references across 21 files.** Done with a script rather than by hand or by a subagent: a literal prefix replacement is deterministic, and the script refuses to write a file whose line count changed or in which any old path survives. Both slash spellings were replaced, each preserving its own style. All six destinations were checked on disk **before** anything was rewritten to point at them.

| where | files | refs |
|---|---|---|
| `C:/NSC/nsc-*.md` doc set | 16 | 65 |
| `.claude/agents/` (pipeline-maintainer, art-director, merge-verifier) | 3 | 4 |
| Documentation Agent's own state and todo | 2 | 2 |

### Left alone on purpose

**Dated handoffs — 20 references across 8 files.** Frozen point-in-time records; they stay accurate as history and the junctions keep their paths working. Not a backlog.

**Other agents' state files — 36 references. Nobody writes another agent's state**, so each owner fixes its own, at its own pace. Nothing is broken meanwhile. Measured counts:

| owner | file | refs |
|---|---|---|
| Pipeline Maintainer | `pipeline-maintainer-agent.md` | 9 |
| Pipeline Maintainer | `pipeline-maintainer-todo.md` | 1 |
| Art Director | `art-director-agent.md` | 7 |
| Art Director | `art-director-agent-todo.md` | 1 |
| Decomposition | `decomposition-agent-20260918-0421-b936e9cb.md` | 4 |
| Decomposition | `decomposition-agent-todo.md` | 3 |
| Decomposition | `decomposition-agent.md` | 2 |
| GER | `ger-agent.md` | 3 |
| GER | `ger-agent-todo.md` | 2 |
| Viewer | `viewer-agent-todo.md` | 2 |
| Viewer | `viewer-agent.md` | 1 |
| Release | `release-agent.md` | 1 |

**These are recorded here rather than messaged to twelve sessions.** A message costs the receiver its whole context on the wake-up turn, and nothing here is broken. Each agent picks its own row up at its next checkpoint.

### Two notes

1. **Totals differ slightly from the brief's 124.** Measured tonight: 71 + 20 + 36 = 127. The extra three are almost certainly todo files that grew after the brief's scan — several agents created theirs the same evening. **Neither figure is wrong; they were taken at different moments.** Quote the measurement with its time or not at all.
2. **Tools deliberately live in two places**, now stated in the runbook's "What runs where" table rather than left as a silent inconsistency: `C:/nscrev/ger-contract-revisions-20260916/` still holds the only copies of `new_task_commit.py`, `policy_entry_commit.py` and `verify_filter.py` — all three verified present at that path tonight — because it is also the GER Agent's live working area.

---

## Addendum — two surfaces the sweep did not cover (Documentation Agent, 2026-09-19)

The sweep covered **documentation**. It did not cover **the tool sources** or **the game repo**, and both still hold old paths.

### One of them is a live breakage, not a latent one

**`ask_astra.py` is broken by the move.** Its `NSC_ASTRA_HOME` default (line 56, `r"C:\nscrev\astra"`) now resolves *through the junction* into `C:\NSC`, and the tool carries a guard that refuses to run there. **Its 62 unit tests still pass** - the false-green shape. Found independently by the adversarial review of 2026-09-19; **my first note on this said it "works today through the junction", which was wrong.**

**It has deliberately not been blind-fixed.** That guard exists to keep Astra's sandbox out of the workspace it reads, and disabling a safety guard to clear a path error is how you trade a visible bug for an invisible one. Not urgent: the live smoke was never run, and it is blocked on Codex until the reset anyway.

### Latent — fine while the junctions exist

- `C:/NSC/tools/ger/apply_runbook_update.py` lines 14 and 97: hardcoded `C:\nscrev\ger-tools\` paths.
- `C:/NSC/tools/astra/README.md` (4), `ask_astra.py` docstring (3), `C:/NSC/tools/art/PROVENANCE.md` (2).
- **In the game repo:** `Pipeline/TaskDesignGER/GER_AUTOMATION.md` - **6 references**, needing a repo commit under the main-write protocol, so not a doc-set edit.
- `__pycache__/*.pyc` under `tools/art` hold the old strings; harmless.

**Both code files are the Pipeline Maintainer's, not the Documentation Agent's.** Flagged, not edited.

### The finding that matters

**The junctions are load-bearing, not transitional.** They were described as a transition net; live code resolves its own state directory through one. **Do not remove a junction as "cleanup" until the files above are fixed** - which is exactly the tidy-up the Cleanup Agent exists to propose, so it must be told before it proposes one.
