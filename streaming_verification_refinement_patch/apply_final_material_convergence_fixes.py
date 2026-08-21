from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECON = ROOT / "Pipeline" / "Reconciliation"
PROMPT_ROOT = RECON / "prompts"
MARKER = "2026-08-21 FINAL MATERIAL CONVERGENCE"

PROMPT_BLOCKS = {
    PROMPT_ROOT / "reconcile.md": r'''

## 2026-08-21 FINAL MATERIAL CONVERGENCE

### Fixed isometric camera provenance

The GDD requires a fixed isometric presentation and no free world-view rotation. Preserve those as the GDD-backed acceptance obligations for `fixed-isometric-camera`.

The current repository also implements player-follow translation through `IsometricCameraFollow.cs`. That follow behavior is a valid current implementation detail and repository-evidence observation, but the current GDD does not require the camera to follow the player. Do not emit player-follow translation as a GDD-backed acceptance criterion and do not cite `GDD - Runtime Implementation` for it. A completed camera item may remain complete when current evidence satisfies the actual fixed-isometric/no-free-rotation requirement.

### Frost Field versus Ranged Enemy attack behavior

The GDD explicitly requires that Frost Field slows a Ranged Enemy's repositioning but does not stop its attacks. Preserve this behavior durably rather than only as background `gdd_evidence`.

At minimum, `enemy-status-effect-displacement` must have a GDD-backed acceptance criterion stating that Frost slowdown modifies locomotion/repositioning only and does not suppress, pause, or slow Ranged Enemy attack execution. `ranged-enemy` should carry a validation requirement that a slowed Ranged Enemy can continue its normal telegraphed attack behavior while movement/repositioning is slowed. Do not create a new work item for this cross-system behavior.
''',
    PROMPT_ROOT / "verification" / "coverage_auditor.md": r'''

## 2026-08-21 FINAL MATERIAL CONVERGENCE

### Explicit representation, not evidence-only coverage

A required runtime behavior is not durably represented merely because its sentence appears in a work item's `gdd_evidence` or because a neighboring acceptance criterion implies it. If an implementer could satisfy the mapped acceptance/validation requirements while violating the GDD behavior, classify that requirement as `unrepresented` (or map it to the explicit criterion that truly obliges it) and emit the corresponding material finding. Do not label an explicitly missing required acceptance/validation obligation as suggestion-only merely because nearby wording makes the intended behavior inferable.

Current canonical example: Frost Field slows Ranged Enemy locomotion/repositioning but does not stop its attacks. Coverage is durable when the status-effect owner explicitly limits the slow to locomotion/repositioning and the Ranged Enemy behavior can be validated to keep attacking while slowed.

For `fixed-isometric-camera`, do not demand player-follow translation as a GDD requirement. The GDD requires fixed isometric presentation/no free rotation; current follow translation is repository implementation behavior unless the GDD is revised to require it.
''',
    PROMPT_ROOT / "verification" / "refiner.md": r'''

## 2026-08-21 FINAL MATERIAL CONVERGENCE

- If `fixed-isometric-camera` presents player-follow translation as GDD-backed acceptance, repair provenance: keep the actual fixed-isometric/no-free-rotation GDD acceptance and move follow behavior to repository evidence/notes as a current implementation detail. Do not downgrade a supported completion claim solely because the extra follow clause was mis-sourced.
- Ensure `enemy-status-effect-displacement` explicitly requires Frost slowdown to affect locomotion/repositioning only without suppressing, pausing, or slowing Ranged Enemy attack execution. Add a Ranged Enemy validation requirement that its normal telegraphed attacks continue while Frost slows movement. This is existing GDD behavior, not new design and not a new work item.
''',
    PROMPT_ROOT / "verification" / "evidence_auditor.md": r'''

## 2026-08-21 FINAL MATERIAL CONVERGENCE

For `fixed-isometric-camera`, distinguish requirement evidence from implementation evidence. Fixed isometric presentation/no free rotation is GDD-backed. Player-follow translation through `IsometricCameraFollow.cs` is valid current repository behavior but must not be presented as a GDD requirement unless the current GDD actually says so.
''',
}


def append_prompt_blocks() -> list[str]:
    changed: list[str] = []
    for path, block in PROMPT_BLOCKS.items():
        text = path.read_text(encoding="utf-8")
        if MARKER in text:
            continue
        path.write_text(text.rstrip() + block + "\n", encoding="utf-8")
        changed.append(path.relative_to(ROOT).as_posix())
    return changed


def patch_refiner_selection() -> bool:
    path = RECON / "verification_crew.py"
    text = path.read_text(encoding="utf-8")

    old = '''    if severity in {"blocker", "error"}:\n        return True\n\n    return (\n        severity == "warning"\n        and category in REFINER_WARNING_CATEGORIES\n    )\n'''
    new = '''    if severity in {"blocker", "error"}:\n        return True\n\n    if severity == "warning" and category in REFINER_WARNING_CATEGORIES:\n        return True\n\n    # Coverage auditors sometimes identify a genuine required-scope\n    # representation gap but conservatively grade it as a suggestion because\n    # nearby evidence implies the intended behavior. Let the bounded Refiner\n    # make that cheap explicitness repair now rather than allowing a different\n    # Pass-2 auditor to promote the same gap to a deterministic material error.\n    source_agent = str(report.get("source_agent", ""))\n    return (\n        severity == "suggestion"\n        and category == "requirement_representation_problem"\n        and source_agent.startswith("Coverage")\n    )\n'''

    if new in text:
        return False
    if old not in text:
        raise RuntimeError("Unable to locate is_refiner_relevant_report selection block.")
    text = text.replace(old, new, 1)

    old_policy = '''            "Refiner input contains all blocker/error findings plus warnings "\n            "whose categories indicate hidden/overgrouped/under-decomposed "\n            "required work. Ordinary warnings and suggestions remain in "\n            "MERGED_FINDINGS_PASS1.json and are reassessed during pass 2. "\n            "This keeps refinement bounded while ensuring scheduler-relevant "\n            "structural warnings are not invisible to the Refiner."\n'''
    new_policy = '''            "Refiner input contains all blocker/error findings, warnings whose "\n            "categories indicate scheduler/representation risk, and coverage-origin "\n            "requirement-representation suggestions. Other ordinary warnings and "\n            "suggestions remain in MERGED_FINDINGS_PASS1.json and are reassessed "\n            "during pass 2. This keeps refinement bounded while preventing a required "\n            "coverage gap noticed in Pass 1 from being stranded until Pass 2."\n'''
    if old_policy in text:
        text = text.replace(old_policy, new_policy, 1)

    path.write_text(text, encoding="utf-8")
    return True


def main() -> int:
    changed_prompts = append_prompt_blocks()
    changed_selection = patch_refiner_selection()

    if changed_prompts:
        print("Installed final material-convergence prompt guidance:")
        for path in changed_prompts:
            print(f"  - {path}")
    else:
        print("Final material-convergence prompt guidance is already installed.")

    if changed_selection:
        print("Coverage requirement-representation suggestions are now Refiner-eligible.")
    else:
        print("Coverage suggestion refinement policy is already installed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
