from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "Pipeline" / "Reconciliation" / "streaming_refinement_v2.py"
MARKER = "semantic list identity for keyed graph fields"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one {label} anchor, found {count}.")
    return text.replace(old, new, 1)


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    if MARKER in text:
        print("Streaming v2 semantic list dedupe is already installed.")
        return 0

    old_helpers = '''def _append_unique(sequence: list[Any], value: Any) -> None:\n    encoded = _canonical(value)\n    if all(_canonical(existing) != encoded for existing in sequence):\n        sequence.append(copy.deepcopy(value))\n\n\ndef _remove_unique(sequence: list[Any], value: Any) -> None:\n    encoded = _canonical(value)\n    sequence[:] = [existing for existing in sequence if _canonical(existing) != encoded]\n'''
    new_helpers = '''# semantic list identity for keyed graph fields\ndef _semantic_list_identity(field: str, value: Any) -> str:\n    # Some graph-list elements have a durable identity independent of explanatory\n    # prose. Two auditors may propose the same dependency/resource key with different\n    # reason/evidence text; that is one semantic element, not two list entries.\n    if field in {"exclusive_resources", "depends_on"} and isinstance(value, dict):\n        key = str(value.get("key", "")).strip()\n        if key:\n            return f"key:{key}"\n    return "value:" + _canonical(value)\n\n\ndef _append_unique(sequence: list[Any], value: Any, *, field: str) -> None:\n    identity = _semantic_list_identity(field, value)\n    if all(_semantic_list_identity(field, existing) != identity for existing in sequence):\n        sequence.append(copy.deepcopy(value))\n\n\ndef _remove_unique(sequence: list[Any], value: Any, *, field: str) -> None:\n    identity = _semantic_list_identity(field, value)\n    sequence[:] = [\n        existing\n        for existing in sequence\n        if _semantic_list_identity(field, existing) != identity\n    ]\n'''
    text = replace_once(text, old_helpers, new_helpers, "append/remove helpers")

    text = text.replace("_append_unique(sequence, value)", "_append_unique(sequence, value, field=field)")
    text = text.replace("_remove_unique(sequence, value)", "_remove_unique(sequence, value, field=field)")

    old_dedupe = '''def _dedupe_operations(operations: list[dict[str, Any]]) -> list[dict[str, Any]]:\n    result: list[dict[str, Any]] = []\n    seen: set[str] = set()\n    for operation in operations:\n        identity = _operation_identity(operation)\n        if identity in seen:\n            continue\n        seen.add(identity)\n        result.append(copy.deepcopy(operation))\n    return result\n'''
    new_dedupe = '''def _operation_effect_identity(operation: dict[str, Any]) -> str:\n    op = str(operation.get("op", "")).strip()\n    target_type = str(operation.get("target_type", "")).strip()\n    target_id = str(operation.get("target_id", "")).strip()\n    field = str(operation.get("field", "")).strip()\n    if op in {"append_unique", "remove_unique"}:\n        value = _decode_value(operation)\n        semantic_value = _semantic_list_identity(field, value)\n        return _canonical({\n            "target_type": target_type,\n            "target_id": target_id,\n            "field": field,\n            "op": op,\n            "semantic_value": semantic_value,\n        })\n    return _operation_identity(operation)\n\n\ndef _dedupe_operations(operations: list[dict[str, Any]]) -> list[dict[str, Any]]:\n    result: list[dict[str, Any]] = []\n    seen: set[str] = set()\n    for operation in operations:\n        identity = _operation_effect_identity(operation)\n        if identity in seen:\n            continue\n        seen.add(identity)\n        result.append(copy.deepcopy(operation))\n    return result\n'''
    text = replace_once(text, old_dedupe, new_dedupe, "operation dedupe")

    TARGET.write_text(text, encoding="utf-8")
    print("Installed semantic dedupe for depends_on/exclusive_resources field operations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
