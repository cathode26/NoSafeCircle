from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()

def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        print(f"already patched: {path}")
        return
    if old not in text:
        raise RuntimeError(f"Expected text not found in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"patched: {path}")

replace_once(
    ROOT / "Pipeline/Reconciliation/reconciliation_agent.py",
    '''ALLOWED_CURRENT_EXACT_PATHS = {
    "Docs/GDD/No_Safe_Circle_GDD.md",
    "Packages/manifest.json",
}''',
    '''ALLOWED_CURRENT_EXACT_PATHS = {
    "Docs/GDD/No_Safe_Circle_GDD.md",
    "Packages/manifest.json",
    "Packages/packages-lock.json",
}'''
)

replace_once(
    ROOT / "Pipeline/Reconciliation/prompts/reconcile.md",
    '''4. `Packages/manifest.json` only when installed Unity package availability materially affects a required implementation''',
    '''4. `Packages/manifest.json` and `Packages/packages-lock.json` only when Unity package declaration or resolved package availability materially affects a required implementation'''
)

reconcile_path = ROOT / "Pipeline/Reconciliation/prompts/reconcile.md"
reconcile_text = reconcile_path.read_text(encoding="utf-8")
marker = "## Package configuration evidence boundary"
block = '''
## Package configuration evidence boundary

When a GDD requirement depends on Unity package availability, the only approved
current-project files under `Packages/` are:

- `Packages/manifest.json` - evidence of directly declared package dependencies;
- `Packages/packages-lock.json` - evidence of the package graph Unity actually
  resolved/locked.

Use `packages-lock.json` only when resolution/transitive package state is
material to the claim. Do not inspect or cite any other file under `Packages/`
as reconciliation evidence unless this source-boundary policy is deliberately
changed later.

A package can be absent from the manifest and absent from the lock file; those
are two compatible but distinct facts. Do not reject valid lock-file evidence
merely because the manifest is the primary package declaration file.
'''.strip()

if marker not in reconcile_text:
    insert_after = (
        "The GDD is root design canon.\n\n"
        "The current checkout is codebase truth for what is integrated."
    )
    if insert_after not in reconcile_text:
        raise RuntimeError("Could not locate reconciliation source-boundary insertion point.")
    reconcile_text = reconcile_text.replace(
        insert_after,
        insert_after + "\n\n" + block,
        1,
    )
    reconcile_path.write_text(reconcile_text, encoding="utf-8")
    print(f"patched: {reconcile_path} (package evidence block)")
else:
    print(f"already patched: {reconcile_path} (package evidence block)")

replace_once(
    ROOT / "Pipeline/Reconciliation/prompts/verification/evidence_auditor.md",
    '''- `Packages/manifest.json` when installed Unity package availability is directly relevant

Do not inspect other files under `Packages/`; only the exact package manifest is
approved as current-project configuration evidence.''',
    '''- `Packages/manifest.json` when declared Unity package availability is directly relevant
- `Packages/packages-lock.json` when resolved/locked Unity package availability is directly relevant

Do not inspect other files under `Packages/`; only the exact manifest and
packages-lock files are approved as current-project configuration evidence.'''
)

replace_once(
    ROOT / "Pipeline/Reconciliation/prompts/verification/evidence_auditor.md",
    '''Read `Packages/manifest.json` exactly when approved package availability is
relevant. Distinguish built-in modules such as `com.unity.modules.tilemap` or
`com.unity.modules.ai` from the GDD-approved packages
`com.unity.2d.tilemap` and `com.unity.ai.navigation`.''',
    '''Read `Packages/manifest.json` when declared package availability is
relevant and `Packages/packages-lock.json` when resolved/locked package state is
material. Distinguish a direct declaration in the manifest from a resolved
entry in the lock file. Also distinguish built-in modules such as
`com.unity.modules.tilemap` or `com.unity.modules.ai` from the GDD-approved
packages `com.unity.2d.tilemap` and `com.unity.ai.navigation`.'''
)

replace_once(
    ROOT / "Pipeline/Reconciliation/verification_smoke_test.py",
    '''    assert reconciliation._is_allowed_review_path("Packages/manifest.json")
    assert not reconciliation._is_allowed_review_path("Packages/packages-lock.json")
''',
    '''    assert reconciliation._is_allowed_review_path("Packages/manifest.json")
    assert reconciliation._is_allowed_review_path("Packages/packages-lock.json")
    assert not reconciliation._is_allowed_review_path("Packages/package-cache.json")
'''
)

print()
print("Package lock boundary fix applied successfully.")
print("No GDD files were changed.")
