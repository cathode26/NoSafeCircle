from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "Pipeline" / "Reconciliation" / "streaming_refinement_v2.py"
MARKER = "record-level remove/upsert conflicts with every field operation"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one {label} anchor, found {count}.")
    return text.replace(old, new, 1)


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    if MARKER in text:
        print("Streaming v2 hardening is already installed.")
        return 0

    old_upsert = '''            if len(existing_indexes) > 1:
                raise StreamRepairError(
                    f"Multiple existing {target_type} records for {target_id!r}."
                )
            if existing_indexes:
                collection[existing_indexes[0]] = copy.deepcopy(value)
            else:
                collection.append(copy.deepcopy(value))
            continue
'''
    new_upsert = '''            if existing_indexes:
                raise StreamRepairError(
                    f"upsert_record is only for genuinely new records; {target_type}:{target_id} already exists."
                )
            collection.append(copy.deepcopy(value))
            continue
'''
    text = replace_once(text, old_upsert, new_upsert, "new-record-only upsert")

    old_conflicts = '''        for target, entries in sorted(operation_entries.items()):
            operations = [operation for _, operation in entries]
            audit_keys = sorted({audit_key for audit_key, _ in entries})
            if len(audit_keys) <= 1:
                continue
            if _field_operations_compatible(operations):
                continue
            conflicting_targets[target] = audit_keys
            for left in audit_keys:
                for right in audit_keys:
                    if left != right:
                        graph[left].add(right)
'''
    new_conflicts = '''        # A record-level remove/upsert conflicts with every field operation on the
        # same record. Expand wildcard entries into the field buckets before deciding
        # whether operations are compatible.
        record_entries: dict[str, list[tuple[str, str, dict[str, Any]]]] = defaultdict(list)
        for target, entries in operation_entries.items():
            target_type, target_id, field = target.split(":", 2)
            record_key = f"{target_type}:{target_id}"
            for audit_key, operation in entries:
                record_entries[record_key].append((field, audit_key, operation))

        for record_key, entries in sorted(record_entries.items()):
            wildcard_entries = [entry for entry in entries if entry[0] == "*"]
            if wildcard_entries:
                audit_keys = sorted({entry[1] for entry in entries})
                if len(audit_keys) > 1:
                    target = f"{record_key}:*"
                    conflicting_targets[target] = audit_keys
                    for left in audit_keys:
                        for right in audit_keys:
                            if left != right:
                                graph[left].add(right)
                continue

            by_field: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
            for field, audit_key, operation in entries:
                by_field[field].append((audit_key, operation))

            for field, field_entries in sorted(by_field.items()):
                operations = [operation for _, operation in field_entries]
                audit_keys = sorted({audit_key for audit_key, _ in field_entries})
                if len(audit_keys) <= 1:
                    continue
                if _field_operations_compatible(operations):
                    continue
                target = f"{record_key}:{field}"
                conflicting_targets[target] = audit_keys
                for left in audit_keys:
                    for right in audit_keys:
                        if left != right:
                            graph[left].add(right)
'''
    text = replace_once(text, old_conflicts, new_conflicts, "record-aware conflict detection")

    TARGET.write_text(text, encoding="utf-8")
    print("Hardened streaming v2 record-level conflict semantics.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
