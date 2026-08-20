# Reconciliation Canonical Coverage Hardening

This patch changes only:

`Pipeline/Reconciliation/prompts/reconcile.md`

## Purpose

Fresh reconciliation was still forgetting requirements that previous
verification/refinement passes had already recovered. This patch adds a mandatory
final canonical-coverage preflight so the generator catches those omissions
before returning JSON.

## Explicit checks added

- concrete enemy health/damage/defeat ownership;
- concrete locked-door enemy attack ownership;
- persistent-state reset completeness, including Player Mana reset support
  before allowing a complete claim;
- one continuous five-space Unity floor/scene representation;
- compile-before-validation process gate;
- isolated workspace and completed-task handoff requirements;
- bounded agent context and no redesign/scope-expansion constraints;
- Development Agent Ownership Invariants;
- generated-development-art import vs gameplay-integration boundary;
- failed-task retry policy;
- player-experience success criteria as validation requirements.

## Intentionally unchanged

- GDD canon;
- Python schemas and deterministic validators;
- dependency-kind rules;
- exclusive-resource rules;
- verification prompts;
- package evidence boundaries;
- AgentCrew/DynamicContentPipeline hard source exclusions;
- Tasks/*.yaml and existing immutable outputs.
