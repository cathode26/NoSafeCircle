"""Opt-in author checklist for D1B.2 decomposition.

Reviewers keep catching the same author mistakes: treating a paired resource
lock as permission to edit a file the parent forbids editing, and omitting
dependencies that a child's own tests require (NSC-088 runs c and d,
2026-09-24). The checklist points the author, the author correction and the
independent reviewer at those checks before the parent's committed contract.

It does not summarise or re-rank the parent. The context keeps the full
contract; the checklist only adds its fixed instruction text and a JSON
pointer, verified against the contract, to every parent acceptance
criterion, completion gate and downstream obligation. Because the checklist
lives in the context payload, it is bound into the context hash the engine
already records. Omitting it leaves the context and prompts byte-identical.
The spec is C:/nscrev/reports/handoffs/three-call-budget-SPEC-20260924.md,
section 3.B.
"""
from __future__ import annotations

from typing import Any

from .context_builder import ContextPackage, DecompositionPreflightError

CHECKLIST_KEY = "author_checklist"

_PARENT_CONTRACT_V1 = """\
Before returning a complete decomposition, check every referenced parent acceptance criterion, \
completion gate, downstream integration obligation, and parent field against all proposed \
children. Preserve each requirement, exception, prohibition, file-edit limit, and test condition.

Compare each child's title, execution reason, decomposition reason, notes, acceptance criteria, \
completion gates, and downstream obligations. They must agree about which files, Components, and \
public methods may change. Requiring an exclusive resource as a lock does not itself permit \
editing that file.

For every existing Component, public method, and production path required by a child's \
implementation or tests, establish its owner from the committed task contracts. Use the task \
catalog to locate candidate owner contracts, then read the relevant contract when it is not \
supplied in full. Include the necessary existing-task and proposed-child dependencies. A resource \
claim is not a dependency; a matching name is not proof of ownership or readiness. Record the \
relevant parent requirement and owner-task references in the child's existing notes or \
requirement references.

Check that each completion gate is locally achievable and that required later assembly or wiring \
has an explicit owner. Do not make a child wait for downstream work that depends on this \
decomposition. Recheck parent coverage after moving work or changing dependencies.

If the committed contracts do not support a necessary decision, report the authority gap through \
the existing result schema. Return only that schema. Do not add checklist fields or claim \
implementation, testing, readiness, approval, or delivery."""

CHECKLIST_VERSIONS = {"parent-contract-v1": _PARENT_CONTRACT_V1}

_ENTRY_COLLECTIONS = (
    ("acceptance_criteria", "criterion_id"),
    ("completion_gates", "gate_id"),
    ("downstream_integration_obligations", "obligation_id"),
)
_PARENT_FIELDS = (
    "execution_reason", "decomposition_reason", "notes",
    "depends_on", "exclusive_resources", "gdd_evidence",
)
_CONTRACT_POINTER = "/selected_task/contract"


def _resolve(payload: dict[str, Any], pointer: str) -> Any:
    value: Any = payload
    for token in pointer.lstrip("/").split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


def _requirement_pointers(contract: dict[str, Any]) -> list[dict[str, str]]:
    pointers = []
    for collection, id_field in _ENTRY_COLLECTIONS:
        entries = contract.get(collection) or []
        if not isinstance(entries, list):
            raise DecompositionPreflightError(f"parent {collection} is not a list")
        for index, entry in enumerate(entries):
            entry_id = entry.get(id_field) if isinstance(entry, dict) else None
            if not isinstance(entry_id, str) or not entry_id:
                raise DecompositionPreflightError(
                    f"parent {collection}[{index}] has no {id_field}; the checklist cannot point at it"
                )
            pointers.append({
                "collection": collection,
                "entry_id": entry_id,
                "pointer": f"{_CONTRACT_POINTER}/{collection}/{index}",
            })
    return pointers


def with_author_checklist(context: ContextPackage, version: str) -> ContextPackage:
    """Return `context` enriched with the named checklist, or refuse."""

    text = CHECKLIST_VERSIONS.get(version)
    if text is None:
        raise DecompositionPreflightError(f"unknown author checklist version {version!r}")
    payload = context.to_dict()
    if CHECKLIST_KEY in payload:
        raise DecompositionPreflightError("context already carries an author checklist")
    contract = payload["selected_task"]["contract"]
    checklist = {
        "version": version,
        "instruction_text": text,
        "unenriched_context_sha256": context.semantic_sha256,
        "requirement_pointers": _requirement_pointers(contract),
        "parent_field_pointers": [
            f"{_CONTRACT_POINTER}/{field}" for field in _PARENT_FIELDS if field in contract
        ],
    }
    payload[CHECKLIST_KEY] = checklist
    enriched = ContextPackage.from_payload(payload)
    verify_author_checklist(enriched)
    return enriched


def verify_author_checklist(context: ContextPackage) -> str | None:
    """Return the checklist version after proving it intact, or None when absent."""

    payload = context.to_dict()
    checklist = payload.get(CHECKLIST_KEY)
    if checklist is None:
        return None
    if not isinstance(checklist, dict):
        raise DecompositionPreflightError("author checklist is not an object")
    version = checklist.get("version")
    if CHECKLIST_VERSIONS.get(version) != checklist.get("instruction_text"):
        raise DecompositionPreflightError(
            "author checklist text does not match its checked-in version"
        )
    contract = payload["selected_task"]["contract"]
    expected = _requirement_pointers(contract)
    if checklist.get("requirement_pointers") != expected:
        raise DecompositionPreflightError(
            "author checklist does not point at exactly the parent's current entries"
        )
    for entry in expected:
        target = _resolve(payload, entry["pointer"])
        id_field = dict(_ENTRY_COLLECTIONS)[entry["collection"]]
        if target.get(id_field) != entry["entry_id"]:
            raise DecompositionPreflightError(f"checklist pointer {entry['pointer']} moved")
    unenriched = dict(payload)
    del unenriched[CHECKLIST_KEY]
    if ContextPackage.from_payload(unenriched).semantic_sha256 != checklist.get("unenriched_context_sha256"):
        raise DecompositionPreflightError("author checklist is bound to a different context")
    return version


def render_author_checklist(context: ContextPackage, *, audience: str) -> str:
    """Prompt text for the checklist, or the empty string when it is absent."""

    version = verify_author_checklist(context)
    if version is None:
        return ""
    text = CHECKLIST_VERSIONS[version]
    if audience == "author":
        lead = "Apply this author checklist before returning your decomposition."
    elif audience == "reviewer":
        lead = (
            "The author was given this checklist. Hold the candidate to it in addition to your "
            "existing review rules, which remain authoritative."
        )
    else:
        raise ValueError(f"unknown checklist audience {audience!r}")
    pointers = "\n".join(
        f"- {entry['entry_id']} ({entry['collection']}): {entry['pointer']}"
        for entry in context.to_dict()[CHECKLIST_KEY]["requirement_pointers"]
    )
    return (
        f"BEGIN AUTHOR CHECKLIST {version}\n{lead}\n\n{text}\n\n"
        f"Parent entries to check, by JSON pointer into the context below:\n{pointers}\n"
        f"END AUTHOR CHECKLIST\n\n"
    )
