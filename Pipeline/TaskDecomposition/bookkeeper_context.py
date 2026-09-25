"""The committed context a bookkeeper needs, and nothing more.

The designer reads the full committed context: the whole GDD, the whole task
catalog and every neighbouring contract, about 190k tokens. The bookkeeper only
writes prose for a design that is already decided, so it gets:

- the parent contract and its identities, unchanged;
- the GDD lines the parent and the ownership sheet cite, numbered, plus the
  GDD's heading index so a reference can name its section;
- each dependency, dependent and the immediate parent as id, title and
  requirement text, not the whole contract;
- the task catalog as id and title only;
- the resource groups, authority notes and source identity, unchanged.

Sibling contracts are dropped. The prompt's instructions, the sheet and the
skeleton are unchanged; see ``bookkeeper_prompts``.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

from .context_builder import ContextPackage

GDD_PATH = "Docs/GDD/No_Safe_Circle_GDD.md"
GDD_CONTEXT_LINES = 2

_CITATION = re.compile(re.escape(GDD_PATH) + r":((?:\d+(?:-\d+)?)(?:\s*,\s*\d+(?:-\d+)?)*)")
_ENTRY_COLLECTIONS = ("acceptance_criteria", "completion_gates", "downstream_integration_obligations")
_KEPT = ("authority_notes", "relevant_resource_groups", "schema_version", "selected_task",
         "selected_task_gdd_evidence", "source_identity")


def cited_gdd_lines(texts: Iterable[str]) -> list[tuple[int, int]]:
    """Every GDD line range cited in the texts, as inclusive (first, last) pairs."""

    ranges: list[tuple[int, int]] = []
    for text in texts:
        for match in _CITATION.finditer(text):
            for part in match.group(1).split(","):
                first, _, last = part.strip().partition("-")
                ranges.append((int(first), int(last or first)))
    return ranges


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def gdd_excerpt(gdd_text: str, ranges: Iterable[tuple[int, int]]) -> dict[str, Any]:
    """The cited lines with a little context, numbered, and the heading index."""

    lines = gdd_text.splitlines()
    wanted: set[int] = set()
    for first, last in ranges:
        low = max(1, min(first, last) - GDD_CONTEXT_LINES)
        high = min(len(lines), max(first, last) + GDD_CONTEXT_LINES)
        wanted.update(range(low, high + 1))
    excerpt: list[str] = []
    previous = 0
    for number in sorted(wanted):
        if previous and number != previous + 1:
            excerpt.append("...")
        excerpt.append(f"{number}: {lines[number - 1]}")
        previous = number
    headings = [f"{number}: {line}" for number, line in enumerate(lines, start=1) if line.startswith("#")]
    return {
        "path": GDD_PATH,
        "note": ("Only the lines cited by the parent contract and the ownership sheet, with "
                 f"{GDD_CONTEXT_LINES} lines either side, prefixed by their line number. Cite GDD "
                 f"lines as {GDD_PATH}:<first>-<last>."),
        "headings": headings,
        "cited_lines": "\n".join(excerpt),
    }


def _contract_summary(contract: Any) -> Any:
    if not isinstance(contract, Mapping):
        return contract
    summary: dict[str, Any] = {key: contract[key] for key in ("id", "title", "depends_on") if key in contract}
    for collection in _ENTRY_COLLECTIONS:
        entries = contract.get(collection)
        if isinstance(entries, list):
            summary[collection] = [entry.get("requirement") for entry in entries
                                   if isinstance(entry, Mapping)]
    return summary


def _summaries(value: Any) -> Any:
    if isinstance(value, list):
        return [_contract_summary(item.get("contract", item)) if isinstance(item, Mapping) else item
                for item in value]
    if isinstance(value, Mapping):
        return _contract_summary(value.get("contract", value))
    return value


def compact_bookkeeper_context(
    context: ContextPackage, sheet: Mapping[str, Any], *, citation_sources: Iterable[Any] = (),
) -> ContextPackage:
    """The bookkeeper's committed context, cut down from the designer's."""

    payload = context.to_dict()
    compact: dict[str, Any] = {key: payload[key] for key in _KEPT if key in payload}
    gdd = payload.get("canonical_gdd")
    if isinstance(gdd, Mapping) and isinstance(gdd.get("full_committed_utf8_text"), str):
        cited = cited_gdd_lines(_strings([payload.get("selected_task"), payload.get("selected_task_gdd_evidence"),
                                          sheet, *citation_sources]))
        compact["canonical_gdd_excerpt"] = {
            "exact_byte_sha256": gdd.get("exact_byte_sha256"),
            **gdd_excerpt(gdd["full_committed_utf8_text"], cited),
        }
    neighbourhood = payload.get("graph_neighborhood")
    if isinstance(neighbourhood, Mapping):
        compact["graph_neighborhood_summary"] = {
            key: _summaries(neighbourhood[key])
            for key in ("dependency_contracts", "direct_dependent_contracts", "immediate_parent_contract")
            if key in neighbourhood
        }
    catalog = payload.get("task_catalog")
    if isinstance(catalog, list):
        compact["task_catalog"] = [{"id": task.get("id"), "title": task.get("title")}
                                   for task in catalog if isinstance(task, Mapping)]
    compact["bookkeeper_context_note"] = (
        "This is a reduced copy of the committed context the designer read. The design is decided; "
        "use it to write references, evidence, notes and reasons. The repository may be inspected "
        "read-only if something needed is missing here.")
    return ContextPackage.from_payload(compact)
