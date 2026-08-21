from __future__ import annotations

import copy
import json
import os
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import verification_crew as base


STREAM_REPAIR_MAX_WORKERS = int(
    os.environ.get("RECONCILIATION_STREAM_REPAIR_MAX_WORKERS", "6")
)
STREAM_REPAIR_MODEL = (
    os.environ.get("RECONCILIATION_STREAM_REPAIR_MODEL", "sonnet").strip()
    or "sonnet"
)
STREAM_CONFLICT_MAX_WORKERS = int(
    os.environ.get("RECONCILIATION_STREAM_CONFLICT_MAX_WORKERS", "4")
)


STREAM_OPERATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "target_type": {
            "type": "string",
            "enum": [
                "work_item",
                "non_code_requirement",
                "deferred_or_excluded",
                "unresolved_question",
                "summary",
                "seed_assessment",
                "sources",
            ],
        },
        "target_id": {"type": "string"},
        "field": {"type": "string"},
        "op": {
            "type": "string",
            "enum": [
                "set",
                "append_unique",
                "remove_unique",
                "remove_record",
                "upsert_record",
            ],
        },
        "value_json": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": [
        "target_type",
        "target_id",
        "field",
        "op",
        "value_json",
        "reason",
    ],
}

STREAM_REPAIR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "schema_version": {"type": "string"},
        "operations": {
            "type": "array",
            "items": STREAM_OPERATION_SCHEMA,
        },
        "finding_resolutions": {
            "type": "array",
            "items": base.REFINER_RESOLUTION_SCHEMA,
            "minItems": 1,
        },
        "reasoning": {"type": "string"},
    },
    "required": [
        "schema_version",
        "operations",
        "finding_resolutions",
        "reasoning",
    ],
}

CONFLICT_ARBITER_SCHEMA = STREAM_REPAIR_SCHEMA


COLLECTION_SPECS: dict[str, tuple[str, str]] = {
    "work_item": ("work_items", "key"),
    "non_code_requirement": ("non_code_requirements", "title"),
    "deferred_or_excluded": ("deferred_or_excluded", "title"),
    "unresolved_question": ("unresolved_questions", "question"),
}

ROOT_OBJECT_TYPES = {
    "summary": "summary",
    "seed_assessment": "seed_assessment",
    "sources": "sources",
}


class StreamRepairError(RuntimeError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _decode_value(operation: dict[str, Any]) -> Any:
    raw = str(operation.get("value_json", ""))
    op = str(operation.get("op", ""))
    if op == "remove_record":
        return None
    if not raw.strip():
        raise StreamRepairError(
            f"{op} operation for {operation.get('target_type')}:{operation.get('target_id')} "
            "requires non-empty value_json."
        )
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise StreamRepairError(
            f"Invalid value_json for operation {operation}: {exc}"
        ) from exc


def _operation_identity(operation: dict[str, Any]) -> str:
    payload = {
        "target_type": operation.get("target_type"),
        "target_id": operation.get("target_id"),
        "field": operation.get("field"),
        "op": operation.get("op"),
        "value_json": operation.get("value_json"),
    }
    return _canonical(payload)


def _operation_target(operation: dict[str, Any]) -> str:
    target_type = str(operation.get("target_type", "")).strip()
    target_id = str(operation.get("target_id", "")).strip()
    field = str(operation.get("field", "")).strip()
    op = str(operation.get("op", "")).strip()
    if op in {"remove_record", "upsert_record"}:
        return f"{target_type}:{target_id}:*"
    return f"{target_type}:{target_id}:{field}"


def _validate_operation_shape(operation: dict[str, Any]) -> None:
    target_type = str(operation.get("target_type", "")).strip()
    target_id = str(operation.get("target_id", "")).strip()
    field = str(operation.get("field", "")).strip()
    op = str(operation.get("op", "")).strip()

    if target_type not in set(COLLECTION_SPECS) | set(ROOT_OBJECT_TYPES):
        raise StreamRepairError(f"Unsupported stream target_type: {target_type!r}")
    if not target_id:
        raise StreamRepairError("Streaming repair operation has blank target_id.")
    if op not in {"set", "append_unique", "remove_unique", "remove_record", "upsert_record"}:
        raise StreamRepairError(f"Unsupported stream operation: {op!r}")

    if target_type in ROOT_OBJECT_TYPES:
        if op in {"remove_record", "upsert_record"}:
            raise StreamRepairError(
                f"Root object {target_type!r} does not support {op!r}."
            )
        if not field:
            raise StreamRepairError(f"{target_type!r} operation requires field.")
    else:
        if op in {"set", "append_unique", "remove_unique"} and not field:
            raise StreamRepairError(
                f"{op!r} operation for {target_type!r} requires field."
            )
        if op in {"remove_record", "upsert_record"} and field:
            raise StreamRepairError(
                f"{op!r} operation must leave field blank."
            )

    _decode_value(operation)


def _find_record(
    payload: dict[str, Any],
    *,
    target_type: str,
    target_id: str,
) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
    collection_name, id_field = COLLECTION_SPECS[target_type]
    collection = payload.setdefault(collection_name, [])
    matches = [
        (index, record)
        for index, record in enumerate(collection)
        if str(record.get(id_field, "")).strip() == target_id
    ]
    if len(matches) != 1:
        raise StreamRepairError(
            f"Expected exactly one {target_type} record {target_id!r}; found {len(matches)}."
        )
    index, record = matches[0]
    return collection, index, record


# semantic list identity for keyed graph fields
def _semantic_list_identity(field: str, value: Any) -> str:
    # Some graph-list elements have a durable identity independent of explanatory
    # prose. Two auditors may propose the same dependency/resource key with different
    # reason/evidence text; that is one semantic element, not two list entries.
    if field in {"exclusive_resources", "depends_on"} and isinstance(value, dict):
        key = str(value.get("key", "")).strip()
        if key:
            return f"key:{key}"
    return "value:" + _canonical(value)


def _append_unique(sequence: list[Any], value: Any, *, field: str) -> None:
    identity = _semantic_list_identity(field, value)
    if all(_semantic_list_identity(field, existing) != identity for existing in sequence):
        sequence.append(copy.deepcopy(value))


def _remove_unique(sequence: list[Any], value: Any, *, field: str) -> None:
    identity = _semantic_list_identity(field, value)
    sequence[:] = [
        existing
        for existing in sequence
        if _semantic_list_identity(field, existing) != identity
    ]


def _operation_changes_record_identity(operation: dict[str, Any]) -> bool:
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
        _validate_operation_shape(operation)
        target_type = str(operation["target_type"]).strip()
        target_id = str(operation["target_id"]).strip()
        field = str(operation["field"]).strip()
        op = str(operation["op"]).strip()
        value = _decode_value(operation)

        if target_type in ROOT_OBJECT_TYPES:
            root_name = ROOT_OBJECT_TYPES[target_type]
            target = payload.setdefault(root_name, {})
            if op == "set":
                target[field] = copy.deepcopy(value)
            elif op == "append_unique":
                sequence = target.setdefault(field, [])
                if not isinstance(sequence, list):
                    raise StreamRepairError(
                        f"{target_type}.{field} is not a list for append_unique."
                    )
                _append_unique(sequence, value, field=field)
            elif op == "remove_unique":
                sequence = target.setdefault(field, [])
                if not isinstance(sequence, list):
                    raise StreamRepairError(
                        f"{target_type}.{field} is not a list for remove_unique."
                    )
                _remove_unique(sequence, value, field=field)
            continue

        collection_name, id_field = COLLECTION_SPECS[target_type]
        collection = payload.setdefault(collection_name, [])

        if op == "upsert_record":
            if not isinstance(value, dict):
                raise StreamRepairError("upsert_record value_json must decode to an object.")
            value_id = str(value.get(id_field, "")).strip()
            if value_id != target_id:
                raise StreamRepairError(
                    f"upsert_record target_id {target_id!r} does not match record {id_field} {value_id!r}."
                )
            existing_indexes = [
                idx
                for idx, record in enumerate(collection)
                if str(record.get(id_field, "")).strip() == target_id
            ]
            if existing_indexes:
                raise StreamRepairError(
                    f"upsert_record is only for genuinely new records; {target_type}:{target_id} already exists."
                )
            collection.append(copy.deepcopy(value))
            continue

        if op == "remove_record":
            if target_type == "work_item" and target_id == "no-safe-circle":
                raise StreamRepairError("Streaming repair may not remove no-safe-circle root.")
            payload[collection_name] = [
                record
                for record in collection
                if str(record.get(id_field, "")).strip() != target_id
            ]
            continue

        _, _, record = _find_record(
            payload,
            target_type=target_type,
            target_id=target_id,
        )
        if op == "set":
            record[field] = copy.deepcopy(value)
        elif op == "append_unique":
            sequence = record.setdefault(field, [])
            if not isinstance(sequence, list):
                raise StreamRepairError(
                    f"{target_type}:{target_id}.{field} is not a list for append_unique."
                )
            _append_unique(sequence, value, field=field)
        elif op == "remove_unique":
            sequence = record.setdefault(field, [])
            if not isinstance(sequence, list):
                raise StreamRepairError(
                    f"{target_type}:{target_id}.{field} is not a list for remove_unique."
                )
            _remove_unique(sequence, value, field=field)

    return payload


def _validate_resolutions(
    repair: dict[str, Any],
    findings: dict[str, Any],
) -> None:
    expected = Counter()
    for report in findings.get("findings", []):
        finding = report.get("finding", {})
        pair = (
            str(report.get("source_agent", "")).strip(),
            str(finding.get("finding_id", "")).strip(),
        )
        if not all(pair):
            raise StreamRepairError("Streaming findings contain missing source_agent/finding_id.")
        expected[pair] += 1

    actual = Counter()
    for resolution in repair.get("finding_resolutions", []):
        pair = (
            str(resolution.get("source_agent", "")).strip(),
            str(resolution.get("finding_id", "")).strip(),
        )
        if not all(pair):
            raise StreamRepairError("Streaming repair contains blank resolution identity.")
        actual[pair] += 1

    if actual != expected:
        missing = list((expected - actual).elements())
        extra = list((actual - expected).elements())
        raise StreamRepairError(
            f"Streaming repair must resolve every supplied finding exactly once; "
            f"missing={missing}, extra={extra}."
        )


def _field_operations_compatible(operations: list[dict[str, Any]]) -> bool:
    if len(operations) <= 1:
        return True

    identities = {_operation_identity(operation) for operation in operations}
    if len(identities) == 1:
        return True

    op_names = {str(operation.get("op", "")) for operation in operations}
    if op_names == {"append_unique"}:
        return True
    if op_names == {"remove_unique"}:
        return True
    if op_names == {"set"}:
        values = {_canonical(_decode_value(operation)) for operation in operations}
        return len(values) == 1

    return False


def _operation_effect_identity(operation: dict[str, Any]) -> str:
    op = str(operation.get("op", "")).strip()
    target_type = str(operation.get("target_type", "")).strip()
    target_id = str(operation.get("target_id", "")).strip()
    field = str(operation.get("field", "")).strip()
    if op in {"append_unique", "remove_unique"}:
        value = _decode_value(operation)
        semantic_value = _semantic_list_identity(field, value)
        return _canonical({
            "target_type": target_type,
            "target_id": target_id,
            "field": field,
            "op": op,
            "semantic_value": semantic_value,
        })
    return _operation_identity(operation)


def _dedupe_operations(operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for operation in operations:
        identity = _operation_effect_identity(operation)
        if identity in seen:
            continue
        seen.add(identity)
        result.append(copy.deepcopy(operation))
    return result


def _legacy_record_delta(
    source: list[dict[str, Any]],
    refined: list[dict[str, Any]],
    *,
    id_field: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    source_map = {str(record.get(id_field, "")).strip(): record for record in source}
    refined_map = {str(record.get(id_field, "")).strip(): record for record in refined}
    upserts: list[dict[str, Any]] = []
    removes: list[str] = []

    for key in sorted(set(source_map) | set(refined_map)):
        before = source_map.get(key)
        after = refined_map.get(key)
        if before is None and after is not None:
            upserts.append(copy.deepcopy(after))
        elif before is not None and after is None:
            removes.append(key)
        elif before != after:
            upserts.append(copy.deepcopy(after))
    return upserts, removes


def build_legacy_refiner_delta(
    *,
    source_payload: dict[str, Any],
    refined_payload: dict[str, Any],
    finding_resolutions: list[dict[str, Any]],
    reasoning: str,
) -> dict[str, Any]:
    work_upserts, work_removes = _legacy_record_delta(
        source_payload.get("work_items", []),
        refined_payload.get("work_items", []),
        id_field="key",
    )
    non_code_upserts, non_code_removes = _legacy_record_delta(
        source_payload.get("non_code_requirements", []),
        refined_payload.get("non_code_requirements", []),
        id_field="title",
    )
    deferred_upserts, deferred_removes = _legacy_record_delta(
        source_payload.get("deferred_or_excluded", []),
        refined_payload.get("deferred_or_excluded", []),
        id_field="title",
    )
    question_upserts, question_removes = _legacy_record_delta(
        source_payload.get("unresolved_questions", []),
        refined_payload.get("unresolved_questions", []),
        id_field="question",
    )

    source_sources = source_payload.get("sources", {})
    refined_sources = refined_payload.get("sources", {})
    source_files = [str(value) for value in source_sources.get("files_reviewed", [])]
    refined_files = [str(value) for value in refined_sources.get("files_reviewed", [])]
    files_add = [value for value in refined_files if value not in source_files]
    source_history = [str(value) for value in source_sources.get("historical_sources_reviewed", [])]
    refined_history = [str(value) for value in refined_sources.get("historical_sources_reviewed", [])]
    history_add = [value for value in refined_history if value not in source_history]

    return {
        "summary": copy.deepcopy(refined_payload.get("summary", source_payload["summary"])),
        "seed_assessment": copy.deepcopy(
            refined_payload.get("seed_assessment", source_payload["seed_assessment"])
        ),
        "files_reviewed_add": files_add,
        "historical_sources_reviewed_add": history_add,
        "work_items_upsert": work_upserts,
        "work_item_keys_remove": work_removes,
        "non_code_requirements_upsert": non_code_upserts,
        "non_code_requirement_titles_remove": non_code_removes,
        "deferred_or_excluded_upsert": deferred_upserts,
        "deferred_or_excluded_titles_remove": deferred_removes,
        "unresolved_questions_upsert": question_upserts,
        "unresolved_question_texts_remove": question_removes,
        "finding_resolutions": copy.deepcopy(finding_resolutions),
        "reasoning": reasoning,
    }


def _local_repair_prompt(
    *,
    source_candidate: Path,
    findings_path: Path,
    source_run_id: str,
) -> str:
    candidate_rel = source_candidate.relative_to(base.ROOT).as_posix()
    findings_rel = findings_path.relative_to(base.ROOT).as_posix()
    # The standard Refiner guidance is inherited by field repair workers so
    # closure/ownership rules remain centralized in prompts/verification/refiner.md.
    refiner_guidance = base.load_prompt("refiner.md")
    return refiner_guidance + f"""

---

# No Safe Circle Streaming Field Repair Worker

You are a READ-ONLY bounded repair worker. One independent verifier completed while
other auditors may still be running. Propose only the smallest field-level edits
needed for this verifier's findings, all relative to the immutable ORIGINAL
reconciliation candidate.

Authority order: current GDD, current repository, verifier evidence, then candidate.
Do not invent design. Do not reproduce complete existing work-item records merely to
change one field.

Inputs:
- Reconciliation source run: `{source_run_id}`
- Immutable candidate: `{candidate_rel}`
- This verifier's selected findings: `{findings_rel}`

Return STREAM_REPAIR_SCHEMA operations.

Operation contract:
- `target_type=work_item` uses target_id = work-item key.
- `target_type=non_code_requirement` uses target_id = title.
- `target_type=deferred_or_excluded` uses target_id = title.
- `target_type=unresolved_question` uses target_id = exact question text.
- `target_type=summary`, `seed_assessment`, or `sources` uses target_id = `root`.
- `set` replaces one field; `value_json` is JSON for the new field value.
- `append_unique` adds ONE element to an existing list field; emit multiple operations
  for multiple additions. `value_json` is JSON for that one element.
- `remove_unique` removes ONE exact element from a list field.
- `remove_record` removes the identified durable record; field and value_json must be empty.
- `upsert_record` is allowed only for a genuinely NEW durable record; field must be empty
  and value_json must contain the full new record object. Never use upsert_record to edit
  an existing work item.

For ordinary acceptance criteria, validation requirements, dependencies, exclusive
resources, evidence, notes, execution scope, confidence, etc., prefer field operations.
Do not change summary or seed_assessment unless a supplied finding directly targets them.
Resolve every supplied finding exactly once. A finding may be rejected as unsupported or
preserved unresolved with zero operations when evidence requires that disposition.
"""


def _cluster_prompt(
    *,
    source_candidate: Path,
    cluster_input: Path,
    source_run_id: str,
) -> str:
    candidate_rel = source_candidate.relative_to(base.ROOT).as_posix()
    cluster_rel = cluster_input.relative_to(base.ROOT).as_posix()
    refiner_guidance = base.load_prompt("refiner.md")
    return refiner_guidance + f"""

---

# No Safe Circle Streaming Field Conflict Arbiter

You are resolving one SMALL connected conflict cluster from streaming repair proposals.
The proposals were independently generated against the same immutable source candidate.
Only audits that actually touched incompatible operations on the same durable field are
included here.

Authority order: current GDD, current repository, verifier evidence, then candidate.
Return STREAM_REPAIR_SCHEMA field operations relative to the ORIGINAL candidate.
Do not rewrite full existing records. Use the same operation contract documented in the
cluster input. Resolve every supplied cluster finding exactly once. Compatible intent may
be synthesized into multiple field operations. Reject unsupported proposal portions.
Preserve unresolved uncertainty instead of inventing game design.

Source run: `{source_run_id}`
Original candidate: `{candidate_rel}`
Cluster input: `{cluster_rel}`
"""


def _merge_resolutions(
    repairs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for repair in repairs:
        for resolution in repair.get("finding_resolutions", []):
            pair = (
                str(resolution.get("source_agent", "")).strip(),
                str(resolution.get("finding_id", "")).strip(),
            )
            if pair in merged and merged[pair] != resolution:
                raise StreamRepairError(
                    f"Conflicting finding resolution emitted for {pair}."
                )
            merged[pair] = copy.deepcopy(resolution)
    return [merged[pair] for pair in sorted(merged)]


class StreamingRepairCoordinator:
    """Field-level streaming repair with deterministic merge and clustered arbitration."""

    def __init__(
        self,
        *,
        source_candidate: Path,
        source_run_id: str,
        run_dir: Path,
    ) -> None:
        self.source_candidate = source_candidate
        self.source_run_id = source_run_id
        self.run_dir = run_dir
        self.root = run_dir / "stream_repairs"
        self.root.mkdir(parents=True, exist_ok=False)
        self.executor = ThreadPoolExecutor(max_workers=max(1, STREAM_REPAIR_MAX_WORKERS))
        self.futures: dict[Any, tuple[Any, Path, dict[str, Any], float]] = {}
        self.repairs: dict[str, dict[str, Any]] = {}
        self.failures: dict[str, str] = {}
        self.conflict_report: dict[str, Any] | None = None
        self.manifest_path = run_dir / "STREAM_REPAIR_MANIFEST.json"
        self.conflict_path = run_dir / "STREAM_CONFLICT_REPORT.json"
        self.arbiter_path = run_dir / "STREAM_CONFLICT_ARBITER.json"
        self.prearbiter_path = run_dir / "STREAM_PREARBITER_CANDIDATE.json"
        self._lock = threading.Lock()
        self._collected = False

    def _run_local_repair(
        self,
        *,
        spec: Any,
        findings_path: Path,
        local_findings: dict[str, Any],
    ) -> dict[str, Any]:
        prompt = _local_repair_prompt(
            source_candidate=self.source_candidate,
            findings_path=findings_path,
            source_run_id=self.source_run_id,
        )
        envelope = base.invoke_read_only_agent(
            agent_name=f"Streaming Field Repair — {spec.key}",
            model=STREAM_REPAIR_MODEL,
            prompt=prompt,
            schema=STREAM_REPAIR_SCHEMA,
            timeout_seconds=base.REFINER_TIMEOUT_SECONDS,
            max_turns=base.REFINER_MAX_TURNS,
        )
        repair = envelope["result"]
        _validate_resolutions(repair, local_findings)
        for operation in repair.get("operations", []):
            _validate_operation_shape(operation)
        return envelope

    def _complete_future(self, future: Any) -> None:
        spec, _, _, submitted = self.futures[future]
        try:
            envelope = future.result()
            with self._lock:
                self.repairs[spec.key] = envelope
            base.save_new_json(
                self.root / spec.key / "PROPOSED_FIELD_REPAIR.json",
                envelope,
            )
            elapsed = round(time.monotonic() - submitted, 2)
            print(f"[STREAM] Field repair completed: {spec.key} ({elapsed}s since submission)")
        except Exception as exc:
            with self._lock:
                self.failures[spec.key] = str(exc)
            print(f"[STREAM] Field repair failed: {spec.key}: {exc}")

    def on_audit_result(self, spec: Any, audit: dict[str, Any]) -> None:
        local_merged = base.merge_findings([audit])
        local_findings = base.build_refiner_findings(local_merged)
        if not local_findings.get("findings"):
            return

        repair_dir = self.root / spec.key
        repair_dir.mkdir(parents=True, exist_ok=False)
        findings_path = repair_dir / "REFINER_FINDINGS.json"
        base.save_new_json(findings_path, local_findings)
        print(
            f"[STREAM] {spec.key} produced refiner-relevant findings; "
            "field repair submitted now."
        )
        submitted = time.monotonic()
        future = self.executor.submit(
            self._run_local_repair,
            spec=spec,
            findings_path=findings_path,
            local_findings=local_findings,
        )
        self.futures[future] = (spec, findings_path, local_findings, submitted)
        future.add_done_callback(self._complete_future)

    def _build_conflict_report(self) -> None:
        operation_entries: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
        proposal_targets: dict[str, list[str]] = {}

        for audit_key, envelope in sorted(self.repairs.items()):
            operations = envelope.get("result", {}).get("operations", [])
            targets: list[str] = []
            for operation in operations:
                target = _operation_target(operation)
                targets.append(target)
                operation_entries[target].append((audit_key, operation))
            proposal_targets[audit_key] = sorted(set(targets))

        conflicting_targets: dict[str, list[str]] = {}
        graph: dict[str, set[str]] = defaultdict(set)

        # A record-level remove/upsert conflicts with every field operation on the
        # same record. Use structured operation fields directly rather than parsing the
        # human-readable target string; titles/questions may legitimately contain colons.
        record_entries: dict[tuple[str, str], list[tuple[str, str, dict[str, Any]]]] = defaultdict(list)
        for entries in operation_entries.values():
            for audit_key, operation in entries:
                target_type = str(operation.get("target_type", "")).strip()
                target_id = str(operation.get("target_id", "")).strip()
                op_name = str(operation.get("op", "")).strip()
                field = "*" if op_name in {"remove_record", "upsert_record"} else str(operation.get("field", "")).strip()
                record_entries[(target_type, target_id)].append((field, audit_key, operation))

        for (target_type, target_id), entries in sorted(record_entries.items()):
            record_label = f"{target_type}:{target_id}"
            wildcard_entries = [entry for entry in entries if entry[0] == "*"]
            if wildcard_entries:
                audit_keys = sorted({entry[1] for entry in entries})
                if len(audit_keys) > 1:
                    target = f"{record_label}:*"
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
                target = f"{record_label}:{field}"
                conflicting_targets[target] = audit_keys
                for left in audit_keys:
                    for right in audit_keys:
                        if left != right:
                            graph[left].add(right)

        components: list[list[str]] = []
        seen: set[str] = set()
        for start in sorted(graph):
            if start in seen:
                continue
            stack = [start]
            component: list[str] = []
            while stack:
                current = stack.pop()
                if current in seen:
                    continue
                seen.add(current)
                component.append(current)
                stack.extend(sorted(graph[current] - seen, reverse=True))
            components.append(sorted(component))

        self.conflict_report = {
            "schema_version": "2.0-field-ops",
            "proposal_count": len(self.repairs),
            "failed_proposal_count": len(self.failures),
            "proposal_targets": proposal_targets,
            "direct_field_conflicts": conflicting_targets,
            "conflict_field_count": len(conflicting_targets),
            "conflict_components": components,
            "conflict_component_count": len(components),
            "policy": (
                "Operations conflict only when independent proposals make incompatible "
                "changes to the same durable field. Compatible append/remove operations "
                "and identical sets merge deterministically. Only connected conflicting "
                "audit components require an LLM arbiter."
            ),
        }
        # This report is derived while the verification run is still in progress;
        # a failed local repair may be recovered before synthesis, so refresh it.
        base.save_json(self.conflict_path, self.conflict_report)

    def collect(self) -> None:
        if self._collected:
            return
        try:
            for future in as_completed(list(self.futures)):
                try:
                    future.result()
                except Exception:
                    pass
        finally:
            self.executor.shutdown(wait=True)
            self._collected = True

        self._build_conflict_report()
        base.save_new_json(
            self.manifest_path,
            {
                "schema_version": "2.0-field-ops",
                "repair_model": STREAM_REPAIR_MODEL,
                "repairs": [
                    {
                        "audit_key": key,
                        "requested_model": envelope.get("requested_model"),
                        "duration_seconds": envelope.get("duration_seconds"),
                        "repair": envelope.get("result"),
                    }
                    for key, envelope in sorted(self.repairs.items())
                ],
                "failures": copy.deepcopy(self.failures),
                "deterministic_conflict_report": self.conflict_report,
            },
        )

    def _run_conflict_cluster(
        self,
        *,
        component_index: int,
        audit_keys: list[str],
        full_findings: dict[str, Any],
        model: str,
    ) -> dict[str, Any]:
        cluster_dir = self.run_dir / "stream_conflicts" / f"cluster_{component_index:02d}"
        cluster_dir.mkdir(parents=True, exist_ok=False)

        source_pairs: set[tuple[str, str]] = set()
        cluster_proposals: list[dict[str, Any]] = []
        for audit_key in audit_keys:
            envelope = self.repairs[audit_key]
            repair = envelope["result"]
            cluster_proposals.append({"audit_key": audit_key, "repair": repair})
            for resolution in repair.get("finding_resolutions", []):
                source_pairs.add(
                    (
                        str(resolution.get("source_agent", "")).strip(),
                        str(resolution.get("finding_id", "")).strip(),
                    )
                )

        cluster_findings = [
            report
            for report in full_findings.get("findings", [])
            if (
                str(report.get("source_agent", "")).strip(),
                str(report.get("finding", {}).get("finding_id", "")).strip(),
            )
            in source_pairs
        ]
        findings_payload = {
            "schema_version": "2.0-cluster",
            "findings": cluster_findings,
        }
        cluster_input = {
            "schema_version": "2.0-field-ops",
            "operation_contract": {
                "set": "replace one field",
                "append_unique": "append one unique list element",
                "remove_unique": "remove one exact list element",
                "remove_record": "remove identified durable record",
                "upsert_record": "create genuinely new durable record only",
            },
            "audit_keys": audit_keys,
            "proposals": cluster_proposals,
            "findings": findings_payload,
        }
        input_path = cluster_dir / "CLUSTER_INPUT.json"
        base.save_new_json(input_path, cluster_input)

        envelope = base.invoke_read_only_agent(
            agent_name=f"Streaming Field Conflict Arbiter {component_index}",
            model=model,
            prompt=_cluster_prompt(
                source_candidate=self.source_candidate,
                cluster_input=input_path,
                source_run_id=self.source_run_id,
            ),
            schema=CONFLICT_ARBITER_SCHEMA,
            timeout_seconds=base.REFINER_TIMEOUT_SECONDS,
            max_turns=base.REFINER_MAX_TURNS,
        )
        repair = envelope["result"]
        _validate_resolutions(repair, findings_payload)
        for operation in repair.get("operations", []):
            _validate_operation_shape(operation)
        base.save_new_json(cluster_dir / "ARBITRATED_FIELD_REPAIR.json", envelope)
        return envelope

    def arbitrate(
        self,
        *,
        full_findings_path: Path,
        model: str,
    ) -> dict[str, Any]:
        self.collect()
        full_findings = base.load_json(full_findings_path)

        for audit_key in sorted(self.failures):
            repair_dir = self.root / audit_key
            findings_path = repair_dir / "REFINER_FINDINGS.json"
            local_findings = base.load_json(findings_path)
            spec_stub = type("SpecStub", (), {"key": audit_key})()
            envelope = self._run_local_repair(
                spec=spec_stub,
                findings_path=findings_path,
                local_findings=local_findings,
            )
            self.repairs[audit_key] = envelope
            base.save_new_json(
                repair_dir / "RECOVERED_FIELD_REPAIR.json",
                envelope,
            )
        if self.failures:
            recovered_failures = sorted(self.failures)
            self.failures.clear()
            self._build_conflict_report()
            manifest = base.load_json(self.manifest_path)
            manifest["repairs"] = [
                {
                    "audit_key": key,
                    "requested_model": envelope.get("requested_model"),
                    "duration_seconds": envelope.get("duration_seconds"),
                    "repair": envelope.get("result"),
                }
                for key, envelope in sorted(self.repairs.items())
            ]
            manifest["failures"] = {}
            manifest["recovered_failures"] = recovered_failures
            manifest["deterministic_conflict_report"] = self.conflict_report
            base.save_json(self.manifest_path, manifest)

        components = list(self.conflict_report.get("conflict_components", [])) if self.conflict_report else []
        conflicted_audits = {key for component in components for key in component}

        accepted_repairs: list[dict[str, Any]] = []
        all_operations: list[dict[str, Any]] = []

        for audit_key, envelope in sorted(self.repairs.items()):
            if audit_key in conflicted_audits:
                continue
            repair = envelope["result"]
            accepted_repairs.append(repair)
            all_operations.extend(repair.get("operations", []))

        if components:
            print(
                f"[STREAM] Field conflicts form {len(components)} cluster(s); "
                f"arbitrating up to {STREAM_CONFLICT_MAX_WORKERS} in parallel."
            )
            cluster_results: dict[int, dict[str, Any]] = {}
            with ThreadPoolExecutor(
                max_workers=max(1, min(STREAM_CONFLICT_MAX_WORKERS, len(components)))
            ) as executor:
                future_map = {
                    executor.submit(
                        self._run_conflict_cluster,
                        component_index=index,
                        audit_keys=component,
                        full_findings=full_findings,
                        model=model,
                    ): index
                    for index, component in enumerate(components, start=1)
                }
                for future in as_completed(future_map):
                    index = future_map[future]
                    cluster_results[index] = future.result()

            for index in sorted(cluster_results):
                repair = cluster_results[index]["result"]
                accepted_repairs.append(repair)
                all_operations.extend(repair.get("operations", []))

        merged_operations = _dedupe_operations(all_operations)
        source_payload = base.load_json(self.source_candidate)
        prearbiter_payload = apply_stream_operations(source_payload, merged_operations)
        base.save_new_json(self.prearbiter_path, prearbiter_payload)

        sanitized_probe = copy.deepcopy(prearbiter_payload)
        base.sanitize_forbidden_evidence(sanitized_probe)
        base.sanitize_refiner_input_tracking(sanitized_probe)
        base.repair_missing_dependency_references(sanitized_probe)
        base.run_semantic_validation(sanitized_probe)

        resolutions = _merge_resolutions(accepted_repairs)
        legacy_delta = build_legacy_refiner_delta(
            source_payload=source_payload,
            refined_payload=prearbiter_payload,
            finding_resolutions=resolutions,
            reasoning=(
                "Streaming refinement v2 merged compatible field-level repair operations "
                "deterministically and arbitrated only connected incompatible field "
                "clusters. The resulting projection passed the normal semantic validator "
                "before conversion to the legacy bounded Refiner delta contract."
            ),
        )
        base.validate_refiner_resolutions(legacy_delta, full_findings)

        envelope = {
            "agent": "Streaming Field Repair Synthesizer",
            "requested_model": model,
            "duration_seconds": 0,
            "result": legacy_delta,
        }
        base.save_new_json(
            self.arbiter_path,
            {
                "schema_version": "2.0-field-ops",
                "field_operation_count": len(merged_operations),
                "conflict_component_count": len(components),
                "legacy_delta": envelope,
            },
        )
        return envelope

    def summary(self) -> dict[str, Any]:
        report = self.conflict_report or {}
        return {
            "enabled": True,
            "version": "2.0-field-ops",
            "repair_model": STREAM_REPAIR_MODEL,
            "repair_max_workers": STREAM_REPAIR_MAX_WORKERS,
            "conflict_max_workers": STREAM_CONFLICT_MAX_WORKERS,
            "proposal_count": len(self.repairs),
            "failed_proposal_count": len(self.failures),
            "mechanical_conflict_count": int(report.get("conflict_field_count", 0)),
            "conflict_component_count": int(report.get("conflict_component_count", 0)),
            "safety_policy": (
                "Early repair workers emit field operations against the immutable source. "
                "Compatible operations merge deterministically. Only connected incompatible "
                "field clusters invoke an arbiter; the final projection must pass normal "
                "semantic validation before conversion to the legacy delta contract."
            ),
        }
