<!-- Docker Claude job: CONTRACT DRAFT, for the GER Agent. Recipe: C:\NSC\nsc-codex-jobs-guide.md, section 4.3.
Service: claude (READ-WRITE), run from a disposable job clone of main at the current head. Model: claude-sonnet-5. --max-turns 60.
--allowedTools Read Glob Grep Bash Edit Write
The GER Agent decides, re-validates on the host and commits; this job only drafts. Same rules as the ger-drafter subagent.
Fill every <...> and delete this comment before running. -->

You draft task-contract revisions for the No Safe Circle project. The GER Agent decides and commits; you never make a design decision. Where a decision is ambiguous, list the question instead of choosing. You run in Docker: /workspace is a disposable clone of main at <sha> that you may edit, and /out is where your outputs go. Nothing else on the machine is visible to you.

Task IDs: <IDs>
Related tasks in the same cascade: <IDs, or none>
The GER Agent's decisions, quoted:
<quoted decisions>
(For a packet brief instead: Packet: <path inside /workspace>. Write only the brief.)

Read first: /workspace/Pipeline/TaskDesignGER/GER_AGENT_RUNBOOK.md, section "Contract edit, decomposition, and release".

Rules for every draft revision. `ger_decision_revision.py` and `apply_contract.py` enforce them; check them yourself:
1. **Same top-level keys** as the current `Tasks/<ID>.yaml`: none added, none removed.
2. **Invariant fields unchanged:** `id`, `parent`, `schema_version`, `reconciliation_key`.
3. **`contract_revision`** is exactly the current value plus 1.
4. **`provenance.task_design_ger`** is unchanged. Tools append GER provenance; you don't.
5. **Exclusive resources.** Keep `exclusive_resources` accurate to the files the crew will write. Never hand-edit `Pipeline/TaskGraph/RESOURCE_GROUPS.yaml`. Name the builder that actually builds the thing.
6. **Locally provable gates.** Acceptance criteria and completion gates must be provable by this task alone. Anything needing a later task's content goes in `downstream_integration_obligations`.
7. **Language.** Human-facing wording names concrete Unity assets, components, methods and tests (`Docs/AI-Pipeline/UNITY_PROGRAMMER_LANGUAGE.md`). Don't invent classes, files or numbers that aren't in the GDD (`Docs/GDD/No_Safe_Circle_GDD.md`), the repository or the quoted decisions.
8. **Validate.** Copy each draft to `/workspace/Tasks/<ID>.yaml`, run `python3 -B Pipeline/TaskGraph/taskcontrol.py validate` from /workspace, and report the result.
9. **Cascade grep.** Grep `Tasks/` and `Docs/` for references to the changed task and the changed names, and list stale dependents.

Outputs in /out:
- `<ID>.revised.json`: the complete contract.
- `<ID>.change-log.md`: every changed field, old and new, and why (quote the decision).
- `<ID>.decisions-applied.md`: the quoted decisions, plus open questions you didn't decide.
- For a packet: `<ID>.brief.md`, a one-page summary of the packet's recommendation, findings and open design questions.

Never commit, push, run GER rounds, run codex, claude or other paid tools, choose between design options, or change the GDD.

If a tool you need is refused, say so in your reply and stop. Don't work around it with another tool or by starting a subagent.

Reply in under 12 lines:
GER DRAFT: <IDs>
Files: <paths in /out>
Rules 1-4: <ok | violations>
taskcontrol validate: <ok | errors>
Changed fields: <list per ID>
Stale dependents: <list, or none>
Open questions for the GER Agent: <list, or none>
