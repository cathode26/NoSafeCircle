from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()

def read(path: str) -> str:
    p = ROOT / path
    if not p.exists():
        raise FileNotFoundError(f"Expected repository file not found: {p}")
    return p.read_text(encoding="utf-8")

def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")

def replace_once(path: str, old: str, new: str, already_marker: str | None = None) -> None:
    text = read(path)
    if already_marker and already_marker in text:
        print(f"already patched: {path}")
        return
    if old not in text:
        raise RuntimeError(f"Expected patch anchor not found in {path}")
    text = text.replace(old, new, 1)
    write(path, text)
    print(f"patched: {path}")

replace_once(
    "Pipeline/Reconciliation/reconciliation_agent.py",
    '''ALLOWED_EXACT_PATHS = {
    "Docs/GDD/No_Safe_Circle_GDD.md",
    "Assignment6GER/README_Assignment6.md",
    "GoalOrientedAgent/outputs/goal_analysis.json",
    "GoalOrientedAgent/outputs/next_goal_selection.json",
}
''',
    '''ALLOWED_CURRENT_EXACT_PATHS = {
    "Docs/GDD/No_Safe_Circle_GDD.md",
    "Packages/manifest.json",
}

ALLOWED_HISTORICAL_PATHS = {
    "Assignment6GER/README_Assignment6.md",
    "GoalOrientedAgent/outputs/goal_analysis.json",
    "GoalOrientedAgent/outputs/next_goal_selection.json",
}

ALLOWED_EXACT_PATHS = ALLOWED_CURRENT_EXACT_PATHS | ALLOWED_HISTORICAL_PATHS
''',
    already_marker='ALLOWED_CURRENT_EXACT_PATHS = {',
)

replace_once(
    "Pipeline/Reconciliation/reconciliation_agent.py",
    '''    invalid_history = [
        str(path)
        for path in historical
        if _normalize_path(str(path)) not in ALLOWED_EXACT_PATHS
        or _normalize_path(str(path))
        == "Docs/GDD/No_Safe_Circle_GDD.md"
    ]
''',
    '''    invalid_history = [
        str(path)
        for path in historical
        if _normalize_path(str(path)) not in ALLOWED_HISTORICAL_PATHS
    ]
''',
    already_marker='if _normalize_path(str(path)) not in ALLOWED_HISTORICAL_PATHS',
)

replace_once(
    "Pipeline/Reconciliation/prompts/reconcile.md",
    '''1. `Docs/GDD/No_Safe_Circle_GDD.md`
2. `Assets/`
3. `ProjectSettings/` only when a GDD requirement genuinely depends on project configuration
''',
    '''1. `Docs/GDD/No_Safe_Circle_GDD.md`
2. `Assets/`
3. `ProjectSettings/` only when a GDD requirement genuinely depends on project configuration
4. `Packages/manifest.json` only when installed Unity package availability materially affects a required implementation
''',
    already_marker='4. `Packages/manifest.json` only when installed Unity package availability',
)

replace_once(
    "Pipeline/Reconciliation/prompts/verification/evidence_auditor.md",
    '''- `Assets/`
- `ProjectSettings/` when relevant
''',
    '''- `Assets/`
- `ProjectSettings/` when relevant
- `Packages/manifest.json` when installed Unity package availability is directly relevant

Do not inspect other files under `Packages/`; only the exact package manifest is
approved as current-project configuration evidence.
''',
    already_marker='Do not inspect other files under `Packages/`',
)

replace_once(
    "Pipeline/Reconciliation/prompts/verification/refiner.md",
    '''1. `Docs/GDD/No_Safe_Circle_GDD.md`
2. current `Assets/`
3. `ProjectSettings/` when relevant
4. the original frozen candidate
5. the merged independent findings
''',
    '''1. `Docs/GDD/No_Safe_Circle_GDD.md`
2. current `Assets/`
3. `ProjectSettings/` when relevant
4. `Packages/manifest.json` when installed Unity package availability is directly relevant
5. the original frozen candidate
6. the merged independent findings

Do not inspect other files under `Packages/`; only the exact package manifest is
approved as current-project configuration evidence.
''',
    already_marker='4. `Packages/manifest.json` when installed Unity package availability',
)

readme_path = "Pipeline/Reconciliation/README.md"
readme = read(readme_path)
if "`Packages/manifest.json`" not in readme:
    anchor = "- `ProjectSettings/` when relevant\n"
    if anchor in readme:
        readme = readme.replace(
            anchor,
            anchor + "- `Packages/manifest.json` when installed package availability is relevant\n",
            1,
        )
        write(readme_path, readme)
        print(f"patched: {readme_path}")
    else:
        print(f"README anchor not found; skipped documentation-only edit: {readme_path}")
else:
    print(f"already patched: {readme_path}")

replace_once(
    "Pipeline/Reconciliation/verification_smoke_test.py",
    '''import random

import verification_crew as crew
''',
    '''import random

import reconciliation_agent as reconciliation
import verification_crew as crew
''',
    already_marker='import reconciliation_agent as reconciliation',
)

replace_once(
    "Pipeline/Reconciliation/verification_smoke_test.py",
    '''    assignments = crew.choose_audit_models(random.Random(12345))

''',
    '''    assignments = crew.choose_audit_models(random.Random(12345))

    assert reconciliation._is_allowed_review_path("Packages/manifest.json")
    assert not reconciliation._is_allowed_review_path("Packages/packages-lock.json")

    valid_history = {
        "sources": {
            "files_reviewed": ["Packages/manifest.json"],
            "historical_sources_reviewed": [
                "Assignment6GER/README_Assignment6.md"
            ],
        }
    }
    reconciliation.validate_reviewed_paths(valid_history)

    invalid_history = {
        "sources": {
            "files_reviewed": ["Packages/manifest.json"],
            "historical_sources_reviewed": ["Packages/manifest.json"],
        }
    }
    try:
        reconciliation.validate_reviewed_paths(invalid_history)
    except RuntimeError:
        pass
    else:
        raise AssertionError(
            "Packages/manifest.json must not be accepted as historical evidence."
        )

''',
    already_marker='assert reconciliation._is_allowed_review_path("Packages/manifest.json")',
)

print()
print("Package-manifest reconciliation boundary fix applied.")
print("Run:")
print("docker compose run --rm claude python3 Pipeline/Reconciliation/verification_smoke_test.py")
print("Then resume the preserved verification with recover_verification.py.")
