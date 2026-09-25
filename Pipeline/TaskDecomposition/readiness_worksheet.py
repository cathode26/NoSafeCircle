"""Decomposition readiness worksheet: what a split must get right, before any paid call.

Most failed decompositions were not bad designs but bookkeeping the author
could not satisfy or did not check: requirement mappings, resource
partitions, test files each child can claim, and dependency owners for
components a child's tests touch (NSC-007, NSC-025, NSC-088 runs c and d).
This worksheet lays those facts out from the committed contracts so an
operator, GER, or the author can see the gaps first. It makes no model call
and changes nothing.

Two parts are text matches, not judgements, and are labelled so: which other
tasks own components the parent's requirements name, and which clauses
restrict edits or reserve decisions. Deterministic code cannot decide what
English grants; the worksheet only points at what a person must read.
Scoped by Astra, rounds 19 and 20.
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping

WORKSHEET_SCHEMA_VERSION = "decomposition-readiness/v1"
_ENTRY_COLLECTIONS = (
    ("acceptance_criteria", "criterion_id"),
    ("completion_gates", "gate_id"),
    ("downstream_integration_obligations", "obligation_id"),
)
_EDIT_RESTRICTION = re.compile(
    r"\b(is not modified|are not modified|not be modified|must not (?:modify|change|edit)|"
    r"does not (?:modify|change|edit)|unchanged|no changes? to|read-only|only as a lock)\b", re.IGNORECASE)
_RESERVED_DECISION = re.compile(
    r"\b(Vincent|human decision|reserved for|to be decided|TBD|requires? approval|design decision)\b",
    re.IGNORECASE)
# A Unity component or class name: CamelCase with at least two capitals.
_COMPONENT_NAME = re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+\b")


def _resource_path(resource: str) -> tuple[str, str]:
    kind, _, path = resource.partition(":")
    return kind, path


def _classify(resources: list[str]) -> dict[str, Any]:
    production, tests, metas, locks = [], [], [], []
    for resource in resources:
        kind, path = _resource_path(resource)
        if kind != "repo-file":
            locks.append(resource)
        elif path.endswith(".meta"):
            metas.append(path)
        elif "/Tests/" in f"/{path}":
            tests.append(path)
        else:
            production.append(path)
    bases = set(production) | set(tests)
    return {
        "production_files": sorted(production),
        "test_files": sorted(tests),
        "scene_or_prefab_locks": sorted(locks),
        "unpaired_meta_files": sorted(m for m in metas if m[: -len(".meta")] not in bases
                                      and PurePosixPath(m[: -len(".meta")]).suffix),
        "separately_claimable_test_files": len(tests),
    }


def _closure(tasks: Mapping[str, Mapping[str, Any]], start: list[str]) -> set[str]:
    seen: set[str] = set()
    pending = list(start)
    while pending:
        task_id = pending.pop()
        if task_id in seen or task_id not in tasks:
            continue
        seen.add(task_id)
        pending.extend(tasks[task_id].get("depends_on") or [])
    return seen


def _requirement_text(contract: Mapping[str, Any]) -> list[dict[str, str]]:
    entries = []
    for collection, id_field in _ENTRY_COLLECTIONS:
        for entry in contract.get(collection) or []:
            if isinstance(entry, Mapping):
                entries.append({"collection": collection, "entry_id": str(entry.get(id_field)),
                                "requirement": str(entry.get("requirement", ""))})
    return entries


def _flag(pattern: re.Pattern, sources: list[tuple[str, str]]) -> list[dict[str, str]]:
    flagged = []
    for where, text in sources:
        for sentence in re.split(r"(?<=[.;])\s+", text):
            if pattern.search(sentence):
                flagged.append({"where": where, "text": sentence.strip()})
    return flagged


def build_worksheet(tasks: Mapping[str, Mapping[str, Any]], task_id: str, *,
                    repository_components: set[str] | frozenset[str] = frozenset()) -> dict[str, Any]:
    """The worksheet for `task_id` from the committed task contracts.

    `repository_components` is the set of production `.cs` file stems in the
    repository; a named identifier that no task claims is reported only when
    it is one of them, so method names and engine types are not noise.
    """

    contract = tasks.get(task_id)
    if contract is None:
        raise ValueError(f"{task_id} is not in the committed graph")
    requirements = _requirement_text(contract)
    declared = list(contract.get("depends_on") or [])
    reachable = _closure(tasks, declared)
    resources = list(contract.get("exclusive_resources") or [])

    text_sources = [(f"{r['entry_id']}", r["requirement"]) for r in requirements]
    text_sources += [(field, str(contract.get(field) or ""))
                     for field in ("execution_reason", "decomposition_reason", "notes")]
    requirement_blob = " ".join(text for _, text in text_sources)

    own_stems = {PurePosixPath(_resource_path(r)[1]).stem for r in resources}
    named = sorted(set(_COMPONENT_NAME.findall(requirement_blob)) - own_stems)
    claimants: dict[str, set[str]] = {}
    for other_id, other in tasks.items():
        if other_id == task_id or other.get("contract_disposition") != "active":
            continue
        for resource in other.get("exclusive_resources") or []:
            kind, path = _resource_path(resource)
            if kind == "repo-file" and path.endswith(".cs") and "/Tests/" not in f"/{path}":
                claimants.setdefault(PurePosixPath(path).stem, set()).add(other_id)
    mentioned: list[dict[str, Any]] = []
    unclaimed: list[str] = []
    for name in named:
        owners = sorted(claimants.get(name, ()))
        if not owners:
            if name in repository_components:
                unclaimed.append(name)
            continue
        mentioned.append({
            "component": name, "owners": owners,
            "declared_owners": [o for o in owners if o in declared],
            "reachable_owners": [o for o in owners if o in reachable],
        })

    return {
        "schema_version": WORKSHEET_SCHEMA_VERSION,
        "task_id": task_id,
        "title": contract.get("title"),
        "contract_revision": contract.get("contract_revision"),
        "execution_scope": contract.get("execution_scope"),
        "decomposition_state": contract.get("decomposition_state"),
        "requirements": requirements,
        "resources": _classify(resources),
        "dependencies": {"declared": declared, "transitive": sorted(reachable - set(declared))},
        "mentioned_components_by_name_match": mentioned,
        "components_with_no_reachable_owner": [m["component"] for m in mentioned if not m["reachable_owners"]],
        "named_identifiers_no_task_claims": unclaimed,
        "edit_restriction_clauses_by_text_match": _flag(_EDIT_RESTRICTION, text_sources),
        "reserved_decision_clauses_by_text_match": _flag(_RESERVED_DECISION, text_sources),
        "decomposition_reason": contract.get("decomposition_reason"),
        "authority": "worksheet_only_not_a_decision",
    }


def render_worksheet_markdown(sheet: Mapping[str, Any]) -> str:
    resources = sheet["resources"]
    lines = [
        f"# Decomposition readiness: {sheet['task_id']} rev {sheet['contract_revision']}",
        "",
        f"**{sheet['title']}** ({sheet['execution_scope']}, {sheet['decomposition_state']})",
        "",
        "Facts from the committed contracts. Name matches and clause flags are text matches for a "
        "person to read, not decisions.",
        "",
        "## Parent requirements (each must map to exactly one child entry)",
        "",
    ]
    lines += [f"- **{r['entry_id']}** ({r['collection']}): {r['requirement']}" for r in sheet["requirements"]]
    lines += ["", "## Resources (each must belong to exactly one child)", "",
              f"- Production files: {len(resources['production_files'])}",
              f"- Test files each child could claim: {resources['separately_claimable_test_files']}",
              f"- Scene/prefab locks: {', '.join(resources['scene_or_prefab_locks']) or 'none'}",
              f"- Unpaired .meta files: {', '.join(resources['unpaired_meta_files']) or 'none'}", ""]
    lines += [f"  - production: `{p}`" for p in resources["production_files"]]
    lines += [f"  - test: `{p}`" for p in resources["test_files"]]
    deps = sheet["dependencies"]
    lines += ["", "## Dependencies", "",
              f"- Declared: {', '.join(deps['declared']) or 'none'}",
              f"- Reachable transitively: {', '.join(deps['transitive']) or 'none'}", "",
              "## Components the requirements name, and who owns them (name match)", ""]
    for m in sheet["mentioned_components_by_name_match"]:
        reach = (", ".join(m["reachable_owners"]) + " reachable") if m["reachable_owners"] else "NO OWNER REACHABLE"
        lines.append(f"- `{m['component']}`: claimed by {', '.join(m['owners'])} ({reach})")
    if not sheet["mentioned_components_by_name_match"]:
        lines.append("- none found")
    if sheet["components_with_no_reachable_owner"]:
        lines += ["", "**Check first:** no owner reachable through dependencies for "
                      f"{', '.join(sheet['components_with_no_reachable_owner'])}. A child whose code or "
                      "tests use one needs its owner as a dependency."]
    if sheet["named_identifiers_no_task_claims"]:
        lines += ["", "**No task claims these by file** (existing code or another task's responsibility; "
                      "a person must name the owner): "
                      f"{', '.join(sheet['named_identifiers_no_task_claims'])}"]
    lines += ["", "## Clauses that restrict edits (text match; a lock is not edit permission)", ""]
    lines += [f"- {c['where']}: {c['text']}" for c in sheet["edit_restriction_clauses_by_text_match"]] or ["- none found"]
    lines += ["", "## Clauses that may reserve a human or design decision (text match)", ""]
    lines += [f"- {c['where']}: {c['text']}" for c in sheet["reserved_decision_clauses_by_text_match"]] or ["- none found"]
    return "\n".join(lines).rstrip() + "\n"


def repository_components(source: Path) -> set[str]:
    """Production C# file stems committed at HEAD under Assets/."""

    import subprocess

    listed = subprocess.run(
        ["git", "-C", str(source), "ls-files", "-z", "--", "Assets/*.cs"],
        check=True, capture_output=True,
    ).stdout.decode("utf-8").split("\0")
    return {PurePosixPath(path).stem for path in listed
            if path and "/Tests/" not in f"/{path}"}


def worksheet_for_source(source: Path, task_id: str) -> dict[str, Any]:
    from persistent_work_graph import load_persistent_work_graph

    return build_worksheet(load_persistent_work_graph(Path(source)).tasks_by_id, task_id,
                           repository_components=repository_components(Path(source)))
