# Verification Closure Hardening

This package addresses the final material issues from verification run
`20260820T071738Z-1b6cc642` plus the previously observed forbidden-source read.

## GDD clarifications

- Makes **Player Health** the explicit single owner of player-health changes.
- Requires an owner-exposed damage interface and restore/heal interface.
- Door lock healing must call Player Health restoration and clamp at max health;
  Door/Interaction never writes player-health state directly.
- Makes the door-to-navigation passability interface an explicit behavioral
  prerequisite when passability publication remains bundled in one executable
  door-lifecycle task.
- States that Section 3 Player Experience Success Criteria are required
  validation obligations rather than advisory prose.
- Labels the reduced-scope/reduced-context failed-task retry rule as a required
  pipeline constraint.

## Reconciliation / verification prompt hardening

Hardens:

- `Pipeline/Reconciliation/prompts/reconcile.md`
- `Pipeline/Reconciliation/prompts/verification/coverage_auditor.md`
- `Pipeline/Reconciliation/prompts/verification/structure_auditor.md`
- `Pipeline/Reconciliation/prompts/verification/execution_scope_auditor.md`
- `Pipeline/Reconciliation/prompts/verification/refiner.md`

The prompts now explicitly enforce:

- Player Health restore ownership and door -> Player Health dependency;
- door passability publication -> navigation-owner dependency when bundled;
- failed-task retry policy -> typed `pipeline_constraint`;
- Section 3 Player Experience Success Criteria -> owning work-item
  `validation_requirements`;
- consistent writer-lock inventory for `Assets/InputSystem_Actions.inputactions`
  only when a work item actually edits that shared asset.

## Hard source boundary

The reconciliation and verification Claude invocations now use tool-level Read
deny rules for:

- `AgentCrew/**`
- `DynamicContentPipeline/**`

This makes the existing source boundary preventative rather than relying only on
prompt compliance and post-generation evidence sanitization. The verification
smoke test asserts that both deny rules are configured.

## Files supplied

- `updated/Docs/GDD/No_Safe_Circle_GDD.md`
- `updated/Docs/GDD/No_Safe_Circle_GDD_Final.docx`
- `apply_verification_closure_hardening.py`

The patch script intentionally does **not** move or overwrite the GDD files.
