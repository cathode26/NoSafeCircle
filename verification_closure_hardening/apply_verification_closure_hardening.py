from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()

PROMPT_BLOCKS = {
    ROOT / "Pipeline/Reconciliation/prompts/reconcile.md": r"""
## Verification-closure ownership and representation preflight

Before returning the reconciliation, explicitly audit the following current-GDD
requirements. These are not optional prompt hints; they are representation and
dependency rules derived from approved canon.

### Player Health restore ownership

Player Health is the single owner of the wizard's current health. If another
system restores health, that system consumes an owner-exposed Player Health
restore interface; it never writes health state directly.

For the current GDD:
- `player-health` must include an acceptance criterion for an owner-controlled
  restore/heal entry point, clamped to maximum health;
- a door lifecycle item that includes lock-and-heal behavior must depend on
  `player-health` (or on the concrete implementation/artifact that owns that
  restore interface if the graph uses a different supported key);
- do not treat a shared-write lock as a substitute for that behavioral
  dependency.

### Door-to-navigation passability dependency

Door and Interaction owns semantic door state. Gameplay navigation/locomotion
owns the shared passability interface that translates that state into enemy
walkability.

If one executable door item includes the acceptance criterion that it publishes
sealed/open/locked/broken state through the navigation-owned passability
interface, that item must depend on the represented navigation/locomotion owner.

If Progressive Decomposition has already split non-navigation door lifecycle
work from passability publication, only the publication/integration child needs
that dependency. Do not over-serialize unrelated door work, but do not leave an
interface prerequisite only in prose.

`logical:gameplay-walkability-surface` is an exclusive-resource collision key,
not an ordering edge.

### Failed-task retry policy

The GDD statement that a failed task is retried with reduced scope/context and
that the whole project is not repeatedly resubmitted for one bug is a REQUIRED
process rule. Represent it in `non_code_requirements` as a typed
`pipeline_constraint` (for example, `Failed-task retry policy`). Do not leave it
only in summary prose or notes.

### Player Experience Success Criteria

Every bullet under GDD Section 3 `Player Experience Success Criteria` is a
required validation obligation. Map those criteria into
`validation_requirements` on the work item(s) that own the underlying behavior.
Do not create duplicate gameplay features just to represent validation.

At minimum preserve explicit validation coverage for:
- understanding that a door requires five safe seconds, not merely reaching it;
- understanding that enemies left alive remain a continuing threat through
  locked-door pressure/breach/persistence;
- readable causes of failure, including positioning, mana pressure, Force Wave
  availability, and waiting too long;
- the existing cursor-drift and encounter-count/cap success criteria.

### Shared Input Actions writer inventory

`Assets/InputSystem_Actions.inputactions` is a single shared JSON asset. For
player-input work items, determine whether the implementation must ADD OR MODIFY
bindings/actions in that asset.

- If yes, include `repo-file:Assets/InputSystem_Actions.inputactions` in
  `exclusive_resources` and normalize that lock across every item expected to
  edit the same asset.
- If an item only consumes an already-existing binding and does not edit the
  asset, do not invent the lock; explain that fact in the item's evidence/notes
  when ambiguity would otherwise remain.
- Re-check Fireball, Frost Field, Force Wave, movement/aim, door interaction,
  and victory-input shutdown as applicable.
""",
    ROOT / "Pipeline/Reconciliation/prompts/verification/coverage_auditor.md": r"""
## Verification-closure coverage mappings

Apply these current-GDD mappings consistently when inventorying requirements:

1. `Player Health ownership` is gameplay ownership, not advisory prose. The
   owner-side restore/heal interface should map to the Player Health work item's
   acceptance criteria; door lock healing maps to the door lifecycle acceptance
   criteria and the appropriate dependency relationship.
2. The failed-task retry rule (`reduce scope and context before retry; do not
   resubmit the entire project for one bug`) is `required_process` represented
   as a typed `pipeline_constraint` in `non_code_requirements`.
3. Every GDD Section 3 `Player Experience Success Criteria` bullet is required
   and should normally map to one or more `validation_requirement` entries on
   the work item(s) that own the behavior. Do not mark those criteria
   `unrepresented` merely because they do not deserve separate work-item nodes.
4. Door passability publication is already owned: Door/Interaction publishes
   semantic state through the navigation-owned passability interface. Coverage
   should not invent a second passability feature; dependency/structure audit
   should verify the prerequisite edge when the publication work is bundled.
""",
    ROOT / "Pipeline/Reconciliation/prompts/verification/structure_auditor.md": r"""
## Verification-closure shared-interface audit

In addition to the general dependency rules, explicitly check these current-GDD
owner/consumer pairs:

- Door lock healing consumes Player Health's owner-exposed restore interface.
  The Player Health owner must be required to expose the interface, and the
  executable door work containing lock-heal must depend on that owner.
- Door semantic-state publication consumes the gameplay
  navigation/locomotion-owned passability interface. If that publication is
  bundled into an executable door lifecycle item, require a dependency on the
  navigation/locomotion owner. If decomposition separates the integration
  child, require the edge only on that child.
- An `exclusive_resources` collision such as
  `logical:gameplay-walkability-surface` does NOT replace a required behavioral
  dependency.

Also perform a shared-writer inventory for
`repo-file:Assets/InputSystem_Actions.inputactions`. If multiple player-input
items are expected to edit the action asset, they should carry the same
exclusive-resource key. Do not require the key when evidence establishes that
an item only consumes an existing binding without modifying the asset.
""",
    ROOT / "Pipeline/Reconciliation/prompts/verification/execution_scope_auditor.md": r"""
## Verification-closure interface/decomposition rule

A broad door-lifecycle item may contain work that is independent of navigation
and a smaller passability-publication responsibility that requires the
navigation-owned interface. Do not solve that distinction by declaring human
integration required.

Accept either:
- a correctly ordered executable item that depends on the navigation owner; or
- `needs_execution_decomposition` when splitting the independent door work from
  the passability-publication child would create safer bounded handoffs.

Likewise, health restoration remains owned by Player Health; door work should
consume that interface rather than absorbing health-state implementation into
its own scope.
""",
    ROOT / "Pipeline/Reconciliation/prompts/verification/refiner.md": r"""
## Verification-closure mandatory repair rules

When refining the candidate, preserve these current-GDD invariants even if an
individual verifier describes the repair differently:

### Health restoration
- Player Health is the sole owner of current player health.
- Ensure the Player Health work item owns a restore/heal entry point clamped to
  maximum health.
- Executable door work that performs lock healing depends on Player Health and
  consumes that interface rather than writing health state directly.

### Door passability
- Navigation/locomotion owns the shared passability interface.
- If passability publication is bundled into the executable door lifecycle
  item, that door item depends on the navigation/locomotion owner.
- If the candidate is execution-decomposed so only a passability integration
  child consumes the interface, put the dependency on that child instead.
- Never use an exclusive-resource key as a substitute for required ordering.

### Required process/validation representation
- Preserve the failed-task reduced-scope/reduced-context retry rule as a typed
  `pipeline_constraint`.
- Preserve every Section 3 Player Experience Success Criterion as a
  `validation_requirement` on the owning work item(s), not merely in notes and
  not as unnecessary new feature nodes.

### Shared Input Actions asset
Normalize `repo-file:Assets/InputSystem_Actions.inputactions` across all work
items that are actually expected to edit that asset. Do not add the lock merely
because an item uses player input if it consumes an existing binding without
editing the asset.

Before returning the refined candidate, re-audit all four areas above.
""",
}

MARKERS = {
    "reconcile.md": "## Verification-closure ownership and representation preflight",
    "coverage_auditor.md": "## Verification-closure coverage mappings",
    "structure_auditor.md": "## Verification-closure shared-interface audit",
    "execution_scope_auditor.md": "## Verification-closure interface/decomposition rule",
    "refiner.md": "## Verification-closure mandatory repair rules",
}


def append_prompt_hardening() -> None:
    for path, block in PROMPT_BLOCKS.items():
        if not path.exists():
            raise FileNotFoundError(f"Expected prompt not found: {path}")
        text = path.read_text(encoding="utf-8-sig")
        marker = MARKERS[path.name]
        if marker in text:
            print(f"Already hardened: {path}")
            continue
        path.write_text(text.rstrip() + "\n\n---\n\n" + block.strip() + "\n", encoding="utf-8")
        print(f"Patched prompt: {path}")


def patch_source_boundary() -> None:
    reconciliation = ROOT / "Pipeline/Reconciliation/reconciliation_agent.py"
    verification = ROOT / "Pipeline/Reconciliation/verification_crew.py"
    smoke = ROOT / "Pipeline/Reconciliation/verification_smoke_test.py"

    for path in (reconciliation, verification, smoke):
        if not path.exists():
            raise FileNotFoundError(f"Expected Python file not found: {path}")

    rtext = reconciliation.read_text(encoding="utf-8")
    constant_marker = "CLAUDE_DISALLOWED_TOOLS = ("
    if constant_marker not in rtext:
        anchor = '''FORBIDDEN_PREFIXES = (\n    "AgentCrew/",\n    "DynamicContentPipeline/",\n)\n'''
        if anchor not in rtext:
            raise RuntimeError("Could not find FORBIDDEN_PREFIXES anchor in reconciliation_agent.py")
        addition = anchor + '''\n# Hard tool-level source boundary. Read deny rules also keep these paths out of\n# Claude file discovery/search for reconciliation and verification invocations.\nCLAUDE_DISALLOWED_TOOLS = (\n    "Edit,Write,mcp__*,"\n    "Read(AgentCrew/**),Read(DynamicContentPipeline/**)"\n)\n'''
        rtext = rtext.replace(anchor, addition, 1)

    old = '        "Edit,Write,mcp__*",\n'
    if old in rtext:
        rtext = rtext.replace(old, '        CLAUDE_DISALLOWED_TOOLS,\n')
    reconciliation.write_text(rtext, encoding="utf-8")
    print(f"Patched source boundary: {reconciliation}")

    vtext = verification.read_text(encoding="utf-8")
    if "    CLAUDE_DISALLOWED_TOOLS,\n" not in vtext:
        import_anchor = "from reconciliation_agent import (\n"
        if import_anchor not in vtext:
            raise RuntimeError("Could not find reconciliation_agent import block in verification_crew.py")
        vtext = vtext.replace(import_anchor, import_anchor + "    CLAUDE_DISALLOWED_TOOLS,\n", 1)
    if old in vtext:
        vtext = vtext.replace(old, '        CLAUDE_DISALLOWED_TOOLS,\n')
    verification.write_text(vtext, encoding="utf-8")
    print(f"Patched source boundary: {verification}")

    stext = smoke.read_text(encoding="utf-8")
    smoke_marker = 'assert "Read(AgentCrew/**)" in reconciliation.CLAUDE_DISALLOWED_TOOLS'
    if smoke_marker not in stext:
        anchor = '    assert not reconciliation._is_allowed_review_path("Packages/packages-lock.json")\n'
        if anchor not in stext:
            raise RuntimeError("Could not find smoke-test path assertions anchor")
        addition = anchor + '''\n    # The model must be blocked before forbidden reconciliation sources can enter context.\n    assert "Read(AgentCrew/**)" in reconciliation.CLAUDE_DISALLOWED_TOOLS\n    assert "Read(DynamicContentPipeline/**)" in reconciliation.CLAUDE_DISALLOWED_TOOLS\n'''
        stext = stext.replace(anchor, addition, 1)
    smoke.write_text(stext, encoding="utf-8")
    print(f"Patched smoke test: {smoke}")


def main() -> int:
    append_prompt_hardening()
    patch_source_boundary()
    print()
    print("Verification-closure hardening applied.")
    print("This script does not copy or replace the GDD files; copy the supplied updated GDD files separately.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
