from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "Pipeline" / "Reconciliation" / "verification_crew.py"
MARKER = "def deterministic_auditor_slug(agent: str) -> str:"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one {label} anchor, found {count}.")
    return text.replace(old, new, 1)


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    if MARKER in text:
        print("Deterministic finding identity fix is already installed.")
        return 0

    # Anchor only on the function definition. Earlier installers may change the
    # amount of whitespace around section comments, so coupling this patch to the
    # exact heading layout makes an otherwise compatible cumulative install fail.
    function_anchor = "def deterministic_audit_checks(audits: list[dict[str, Any]]) -> list[dict[str, Any]]:\n"
    function_replacement = '''def deterministic_auditor_slug(agent: str) -> str:
    """Return a stable identifier safe for deterministic finding IDs."""
    slug = "".join(
        character.lower() if character.isalnum() else "-"
        for character in str(agent)
    )
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "unknown-auditor"


def deterministic_audit_checks(audits: list[dict[str, Any]]) -> list[dict[str, Any]]:
'''
    text = replace_once(
        text,
        function_anchor,
        function_replacement,
        "deterministic audit function",
    )

    id_anchor = '''                        "finding_id": (
                            "deterministic-representation-"
                            + str(requirement.get("requirement_id", "unknown"))
                        ),
'''
    id_replacement = '''                        "finding_id": (
                            "deterministic-representation-"
                            + deterministic_auditor_slug(agent)
                            + "-"
                            + str(requirement.get("requirement_id", "unknown"))
                        ),
'''
    text = replace_once(
        text,
        id_anchor,
        id_replacement,
        "deterministic finding ID",
    )

    TARGET.write_text(text, encoding="utf-8")
    print("Deterministic requirement findings now include the originating auditor identity.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
