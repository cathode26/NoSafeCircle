from __future__ import annotations

from pathlib import Path
import re

ROOT = Path.cwd()
PATH = ROOT / "Pipeline/Reconciliation/verification_smoke_test.py"

if not PATH.exists():
    raise FileNotFoundError(PATH)

text = PATH.read_text(encoding="utf-8")


def set_mapping(requirement_id: str, titles: list[str]) -> None:
    global text

    # Locate one requirement dictionary by requirement_id, then replace the
    # mapped_non_code_titles line inside that dictionary only.
    marker = f'"requirement_id": "{requirement_id}"'
    start = text.find(marker)
    if start < 0:
        raise RuntimeError(f"Could not find smoke-test requirement {requirement_id!r}")

    # Requirement dictionaries in this smoke test are compact; stop at the next
    # requirement_id or the end of the enclosing list.
    next_req = text.find('"requirement_id":', start + len(marker))
    end = next_req if next_req >= 0 else len(text)
    block = text[start:end]

    replacement = (
        '"mapped_non_code_titles": '
        + repr(titles).replace("'", '"')
        + ","
    )

    if '"mapped_non_code_titles":' in block:
        new_block, count = re.subn(
            r'"mapped_non_code_titles":\s*\[[^\]]*\],',
            replacement,
            block,
            count=1,
        )
        if count != 1:
            raise RuntimeError(
                f"Could not rewrite mapped_non_code_titles for {requirement_id}"
            )
    else:
        anchor = '"mapped_keys":'
        anchor_pos = block.find(anchor)
        if anchor_pos < 0:
            raise RuntimeError(
                f"Could not find mapped_keys for {requirement_id}"
            )
        line_end = block.find("\n", anchor_pos)
        if line_end < 0:
            raise RuntimeError(
                f"Could not find mapped_keys line ending for {requirement_id}"
            )
        indent_start = block.rfind("\n", 0, anchor_pos) + 1
        indent = block[indent_start:anchor_pos]
        new_block = (
            block[: line_end + 1]
            + indent
            + replacement
            + "\n"
            + block[line_end + 1 :]
        )

    text = text[:start] + new_block + text[end:]


# These are the two valid typed non-code examples in taxonomy_ok. They must map
# to a durable non-code record title rather than an empty list.
set_mapping("REQ-PIPELINE", ["No concurrent Unity asset edits"])
set_mapping("REQ-DELIVERY", ["Windows build"])

# Improve the failing assertion so any future taxonomy regression prints the
# exact deterministic findings rather than only "AssertionError".
old = '    assert crew.deterministic_audit_checks(taxonomy_ok) == []\n'
new = (
    '    taxonomy_ok_findings = crew.deterministic_audit_checks(taxonomy_ok)\n'
    '    assert taxonomy_ok_findings == [], taxonomy_ok_findings\n'
)
if old in text:
    text = text.replace(old, new, 1)
elif "taxonomy_ok_findings = crew.deterministic_audit_checks(taxonomy_ok)" not in text:
    raise RuntimeError("Could not find taxonomy_ok assertion to improve.")

PATH.write_text(text, encoding="utf-8")

# Verify the two mappings really landed in the intended blocks.
for requirement_id, expected in (
    ("REQ-PIPELINE", '"mapped_non_code_titles": ["No concurrent Unity asset edits"]'),
    ("REQ-DELIVERY", '"mapped_non_code_titles": ["Windows build"]'),
):
    start = text.find(f'"requirement_id": "{requirement_id}"')
    if start < 0:
        raise RuntimeError(f"Missing {requirement_id} after patch")
    next_req = text.find('"requirement_id":', start + 1)
    block = text[start : next_req if next_req >= 0 else len(text)]
    if expected not in block:
        raise RuntimeError(
            f"{requirement_id} still does not contain expected non-code mapping."
        )

print("Fixed typed non-code taxonomy smoke-test mappings.")
print("Next command:")
print(
    "docker compose run --rm claude python3 "
    "Pipeline/Reconciliation/verification_smoke_test.py"
)
