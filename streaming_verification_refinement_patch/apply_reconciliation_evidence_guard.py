from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMPT = ROOT / "Pipeline" / "Reconciliation" / "prompts" / "reconcile.md"
MARKER = "2026-08-21 EVIDENCE PATH PRECISION"

SECTION = r'''
---

## 2026-08-21 EVIDENCE PATH PRECISION

Repository evidence must identify a concrete repository-relative evidence path.

Do not emit broad container roots such as:

```text
Assets
Assets/
ProjectSettings
ProjectSettings/
```

as `repository_evidence[].path` or `sources.files_reviewed`. Those names describe
inspection territory, not evidence for a repository-state claim.

Use the exact file that supports the observation, for example:

```text
Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerMovement.cs
Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity
ProjectSettings/EditorBuildSettings.asset
Packages/manifest.json
```

If a broad scan found no implementation, do not manufacture a directory path as
negative evidence. Cite the concrete files/configuration actually inspected when
available, or leave repository evidence empty and describe the absence precisely
in repository state/notes. The semantic validator intentionally rejects bare
repository container roots.
'''


def main() -> int:
    text = PROMPT.read_text(encoding="utf-8-sig")
    if MARKER in text:
        print("Reconciliation evidence-path guard is already installed.")
        return 0
    if not text.endswith("\n"):
        text += "\n"
    text += "\n" + SECTION.strip() + "\n"
    PROMPT.write_text(text, encoding="utf-8", newline="\n")
    print(f"Installed reconciliation evidence-path guard in {PROMPT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
