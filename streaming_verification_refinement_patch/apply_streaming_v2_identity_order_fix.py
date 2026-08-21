from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "Pipeline" / "Reconciliation" / "streaming_refinement_v2.py"
MARKER = "def _operation_changes_record_identity("


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one {label} anchor, found {count}.")
    return text.replace(old, new, 1)


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    if MARKER in text:
        print("Streaming v2 identity-field ordering fix is already installed.")
        return 0

    anchor = '''def apply_stream_operations(
    source_payload: dict[str, Any],
    operations: list[dict[str, Any]],
) -> dict[str, Any]:
    payload = copy.deepcopy(source_payload)

    for operation in operations:
'''

    replacement = '''def _operation_changes_record_identity(operation: dict[str, Any]) -> bool:
    """Return True when an operation changes the durable lookup identity of a record.

    Streaming repair operations are always expressed relative to the immutable source
    candidate. If a repair both edits a record and renames its identity field, all edits
    that still target the original identity must run before the rename.
    """
    target_type = str(operation.get("target_type", "")).strip()
    if target_type not in COLLECTION_SPECS:
        return False
    _, id_field = COLLECTION_SPECS[target_type]
    return (
        str(operation.get("op", "")).strip() == "set"
        and str(operation.get("field", "")).strip() == id_field
    )


def apply_stream_operations(
    source_payload: dict[str, Any],
    operations: list[dict[str, Any]],
) -> dict[str, Any]:
    payload = copy.deepcopy(source_payload)

    # Every operation is addressed against the ORIGINAL immutable candidate. A set on
    # a collection identity field (work_item.key, non-code/deferred title, or unresolved
    # question text) therefore has to be applied after every non-identity edit. Preserve
    # original relative ordering inside each group so the repair remains deterministic.
    indexed_operations = list(enumerate(operations))
    indexed_operations.sort(
        key=lambda pair: (
            1 if _operation_changes_record_identity(pair[1]) else 0,
            pair[0],
        )
    )

    for _, operation in indexed_operations:
'''

    text = replace_once(
        text,
        anchor,
        replacement,
        "apply_stream_operations identity-ordering",
    )

    TARGET.write_text(text, encoding="utf-8")
    print("Streaming v2 now applies record-identity field changes after other source-addressed edits.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
