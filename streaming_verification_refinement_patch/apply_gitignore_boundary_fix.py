from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECON = ROOT / "Pipeline" / "Reconciliation"
RECON_AGENT = RECON / "reconciliation_agent.py"
RECON_PROMPT = RECON / "prompts" / "reconcile.md"

MARKER = "CURRENT REPOSITORY METADATA BOUNDARY 2026-08-21"

PROMPT_BLOCK = r'''

## CURRENT REPOSITORY METADATA BOUNDARY 2026-08-21

`/.gitignore` is an approved current-project metadata source only for narrow
source-control/current-checkout questions. In particular, it may be inspected to
establish whether Unity editor/user-local state such as `UserSettings/` is
intentionally excluded from the committed repository.

This does NOT make `.gitignore` design canon or gameplay evidence. Do not use it
to invent requirements, dependencies, ownership rules, acceptance criteria, or
exclusive-resource decisions. No other root-level repository metadata file is
approved by this exception unless the boundary is deliberately expanded later.
'''


def patch_agent() -> bool:
    text = RECON_AGENT.read_text(encoding="utf-8")
    changed = False

    if '    ".gitignore",\n' not in text:
        anchor = '''ALLOWED_CURRENT_EXACT_PATHS = {\n    "Docs/GDD/No_Safe_Circle_GDD.md",\n'''
        replacement = '''ALLOWED_CURRENT_EXACT_PATHS = {\n    "Docs/GDD/No_Safe_Circle_GDD.md",\n    ".gitignore",\n'''
        if text.count(anchor) != 1:
            raise RuntimeError("Unable to locate current exact-path boundary anchor.")
        text = text.replace(anchor, replacement, 1)
        changed = True

    old_normalizer = '''def _normalize_path(value: str) -> str:\n    return value.replace("\\\\", "/").lstrip("./")\n'''
    new_normalizer = '''def _normalize_path(value: str) -> str:\n    path = value.replace("\\\\", "/")\n    while path.startswith("./"):\n        path = path[2:]\n    if path.startswith("/"):\n        path = path[1:]\n    return path\n'''
    if old_normalizer in text:
        text = text.replace(old_normalizer, new_normalizer, 1)
        changed = True
    elif new_normalizer not in text:
        raise RuntimeError("Unable to locate reconciliation path normalizer.")

    if changed:
        RECON_AGENT.write_text(text, encoding="utf-8")
    return changed


def patch_prompt() -> bool:
    text = RECON_PROMPT.read_text(encoding="utf-8")
    if MARKER in text:
        return False
    RECON_PROMPT.write_text(text.rstrip() + PROMPT_BLOCK + "\n", encoding="utf-8")
    return True


def main() -> int:
    agent_changed = patch_agent()
    prompt_changed = patch_prompt()

    if agent_changed or prompt_changed:
        print("Installed narrow .gitignore reconciliation boundary fix.")
        if agent_changed:
            print("  - .gitignore is now an allowed exact current-project review path.")
            print("  - Path normalization now preserves root dotfiles such as .gitignore.")
        if prompt_changed:
            print("  - Prompt limits .gitignore to source-control/current-checkout metadata.")
    else:
        print("Narrow .gitignore reconciliation boundary fix is already installed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
