# GDD + Reconciliation Verification Pass Hardening

This package targets the remaining ambiguity and bookkeeping issues found after the successful reconciliation/verification run that reduced 18 pass-1 material findings to 4 final material findings.

## GDD clarifications

- Explicitly require continuous player-facing health feedback.
- Explicitly place the wizard and enemies in the world-space SpriteRenderer visual foundation and isometric sorting rules.
- Approve Unity 2D Tilemap Editor (`com.unity.2d.tilemap`) for Isometric Tilemap authoring.
- Approve Unity AI Navigation (`com.unity.ai.navigation`) and NavMesh-based runtime movement for enemy navigation.
- Remove the obsolete unresolved-navigation-technology decision.
- Make pursuit/search state a prerequisite contract consumed by status-effect/displacement hand-back.
- Clarify that full floor restart resets all run-persistent gameplay state, while allowing truthful staged validation before all five rooms exist.
- Make deferred five-room content and encounter content explicitly consume their reusable foundations.
- Define Windows Standalone build configuration as concrete project configuration: the canonical gameplay scene must be registered in Build Settings.
- Clarify that missing approved packages or missing Build Settings scene registration are actionable implementation/configuration work, not deferred design.

## Agent prompt hardening

Updates six prompts:

- `Pipeline/Reconciliation/prompts/reconcile.md`
- `Pipeline/Reconciliation/prompts/verification/coverage_auditor.md`
- `Pipeline/Reconciliation/prompts/verification/evidence_auditor.md`
- `Pipeline/Reconciliation/prompts/verification/structure_auditor.md`
- `Pipeline/Reconciliation/prompts/verification/execution_scope_auditor.md`
- `Pipeline/Reconciliation/prompts/verification/refiner.md`

The new rules:

- distinguish required delivery obligations from concrete missing configuration prerequisites;
- treat approved package absence as missing configuration, not an unresolved architecture choice;
- promote real dependencies out of free-text notes;
- preserve pursuit/search -> status/displacement hand-back ordering;
- normalize exclusive-resource locks across all writers, not just the pair named in one finding;
- inspect `.inputactions` assets before making project-wide negative cursor-input claims;
- require serialized scene/prefab/config evidence for integration-sensitive completion claims;
- represent visible health feedback under Player Health;
- represent wizard/enemy SpriteRenderer presentation under the visual-world foundation;
- allow truthful staged restart validation without pretending five-room content already exists.

The prompt patch script does not copy or move GDD files. Replace the Markdown/DOCX manually, then run the prompt patch script from the repository root.
