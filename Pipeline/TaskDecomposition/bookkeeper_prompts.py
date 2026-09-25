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
from .bookkeeping_skeleton import result_skeleton
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

You are not designing this split. A designer has already decided it (the ownership sheet below),
and code has already built every structural field of the result from it (the result skeleton
below): the children, entry IDs, requirements, coverage table and dependency rewrites. Return the
complete decomposition result JSON: the skeleton with every empty prose field written.

- each entry's `reference`: the parent contract entry or GDD section it comes from.
- each child's `gdd_evidence`, `basis`, `confidence`, `source_scope`, `decomposition_state` and
  `decomposition_reason`, following the rules above.
- each child's `notes`: keep the designer's notes that are already there and add what the rules
  above require.
- each coverage record's `reason`, and an `integration_rationale` where the disposition is
  "shared_integration".
- each inbound dependency rewrite's `reason`; the top-level `reason` follows the sheet's
  rationale. Also fill `schema_version`, `parent_task`, `gap_type`, `unresolved_questions`,
  `unsupported_assumptions` and `artifact_proposal` as the rules above require.

Code restores every structural field from the skeleton afterwards, so changing one has no effect.
If the design cannot be written as a valid result, say exactly what is wrong in the top-level
`reason`.

### Ownership sheet
```json
"""


def _sheet_json(sheet: Mapping[str, Any]) -> str:
    return json.dumps(sheet, indent=1, ensure_ascii=False, sort_keys=True)


def build_designer_prompt(context: ContextPackage) -> str:
    return build_decomposer_prompt(context) + _DESIGNER_MODE


def build_designer_correction_prompt(
    context: ContextPackage, *, rejected_sheet: Any, rejection_reason: str,
) -> str:
    return build_designer_prompt(context) + f"""

## CORRECTION: your previous ownership sheet was refused

Deterministic checks refused the sheet below for this reason:

{rejection_reason}

Return a corrected, complete ownership sheet that fixes this and keeps every other decision that
was sound. This is the only correction.

### Refused sheet
```json
{json.dumps(rejected_sheet, indent=1, ensure_ascii=False, sort_keys=True)}
```
"""


def build_bookkeeper_prompt(context: ContextPackage, sheet: Mapping[str, Any]) -> str:
    return (build_decomposer_prompt(context) + _BOOKKEEPER_MODE + _sheet_json(sheet)
            + "\n```\n\n### Result skeleton\n```json\n" + _sheet_json(result_skeleton(sheet)) + "\n```\n")


def build_bookkeeper_retry_prompt(
    sheet: Mapping[str, Any], rejected: Any, problems: Iterable[str],
) -> str:
    listed = "\n".join(f"- {problem}" for problem in problems)
    return f"""You wrote a decomposition result from a designer's ownership sheet. Deterministic checks \
found these problems:

{listed}

Return the corrected complete decomposition result JSON. Fix only these problems, in the prose \
fields (references, evidence, notes, reasons and the child classification fields). Code restores every \
structural field from the sheet afterwards, so the children, entry IDs, requirements, coverage links and \
dependencies in your previous result are already right; change nothing else.

### Ownership sheet
```json
{_sheet_json(sheet)}
```

### Your previous result
```json
{json.dumps(rejected, indent=1, ensure_ascii=False, sort_keys=True)}
```
"""
