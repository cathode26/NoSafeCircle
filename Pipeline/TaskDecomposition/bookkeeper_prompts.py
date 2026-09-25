"""Prompts for the opt-in designer/bookkeeper split of the D1B.2 author round.

The designer receives the ordinary author prompt and writes only an ownership
sheet. The bookkeeper receives the same prompt plus the frozen sheet and
writes the complete decomposition result that states it. A bookkeeper retry
receives only the sheet, its rejected result and the exact problems found.
"""
from __future__ import annotations

import json
from typing import Any, Iterable, Mapping

from .context_builder import ContextPackage
from .prompts import build_decomposer_prompt

_DESIGNER_MODE = """

## DESIGN MODE: return an ownership sheet, not a decomposition result

In this run the decomposition is written in two steps. You make every design decision; a
separate bookkeeping step later writes the complete result schema from your sheet without
changing it. So return ONLY the ownership sheet schema. Where the instructions above refer to
the result schema, coverage records, entry IDs or references, apply them to the sheet like this:

- `children`: every proposed child with its final `local_key`, `title`, `kind`, `type` and
  `execution_scope`. `purpose` becomes the child's execution_reason word for word.
- `exclusive_resources`, `existing_task_dependencies` and `local_dependencies`: final, exact.
  Every resource belongs to exactly one child.
- `entries`: every acceptance criterion, completion gate and downstream integration obligation of
  the child, with its FINAL requirement text. Each child needs at least one acceptance criterion
  and one completion gate. `covers` lists the parent entries that child entry satisfies, written
  `acceptance_criteria:AC-001`, `completion_gates:VAL-002` or
  `downstream_integration_obligations:INT-003`. Every parent entry must be covered by at least one
  child entry. Distinct parent entries of one type need distinct child entries.
- `design_notes`: the owner-task references and constraints the child's notes must record.
- `inbound_dependency_rewrites`: every existing task that depends on the parent and the children
  it must depend on instead.
- `rationale`: why the split is shaped this way.

Do not write entry IDs, references, reasons or coverage records; the bookkeeping step does that.
"""

_BOOKKEEPER_MODE = """

## BOOKKEEPING MODE: the design is already decided

You are not designing this split. A designer has already decided it, and its ownership sheet is
below. Write the complete decomposition result JSON that states exactly this design, filling in
only the bookkeeping:

- decision "decomposed"; one child per sheet child, with the same local_key, title, kind, type and
  execution_scope; execution_reason is the sheet's purpose, copied exactly.
- exclusive_resources, existing_task_dependencies and local_dependencies copied exactly.
- each sheet entry becomes one child entry of its entry_type with its requirement copied EXACTLY,
  character for character. Assign IDs (AC-001.., VAL-001.., INT-001.. within each child) and write
  each entry's reference from the parent contract or GDD.
- parent_requirement_coverage: one record per parent entry. Its child_targets are the child
  entries whose sheet `covers` names that parent entry ("acceptance_criteria:AC-001" means
  parent_entry_type acceptance_criteria, parent_entry_id AC-001). A parent entry covered by
  entries in two or more children is "shared_integration" with an integration_rationale;
  otherwise "assigned_to_child" with an empty integration_rationale.
- each child's notes include its sheet design_notes.
- inbound_dependency_rewrites exactly as in the sheet, each with a reason; the top-level reason
  follows the sheet's rationale.
- fill every other field consistently with the rules above.

Do not add, remove, merge, split or reword any child, resource, dependency, requirement or
coverage link. If the sheet cannot be written as a valid result without changing the design,
write the closest result and state exactly what is wrong in the top-level `reason`.

### Ownership sheet
```json
"""


def _sheet_json(sheet: Mapping[str, Any]) -> str:
    return json.dumps(sheet, indent=1, ensure_ascii=False, sort_keys=True)


def build_designer_prompt(context: ContextPackage) -> str:
    return build_decomposer_prompt(context) + _DESIGNER_MODE


def build_bookkeeper_prompt(context: ContextPackage, sheet: Mapping[str, Any]) -> str:
    return build_decomposer_prompt(context) + _BOOKKEEPER_MODE + _sheet_json(sheet) + "\n```\n"


def build_bookkeeper_retry_prompt(
    sheet: Mapping[str, Any], rejected: Any, problems: Iterable[str],
) -> str:
    listed = "\n".join(f"- {problem}" for problem in problems)
    return f"""You wrote a decomposition result from a designer's ownership sheet. Deterministic checks \
found these problems:

{listed}

Return the corrected complete decomposition result JSON. Fix only these problems: every sheet entry \
must appear as its own child entry with its requirement copied exactly, and each parent entry's \
coverage must point at exactly the child entries whose sheet `covers` names it. Renumber IDs within a \
child if you need to, and keep every coverage record pointing at the right entry after renumbering. \
Change nothing else.

### Ownership sheet
```json
{_sheet_json(sheet)}
```

### Your previous result
```json
{json.dumps(rejected, indent=1, ensure_ascii=False, sort_keys=True)}
```
"""
