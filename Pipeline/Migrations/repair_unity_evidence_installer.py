#!/usr/bin/env python3
"""Make generated Python templates raw so escape sequences remain source text."""

from __future__ import annotations

from pathlib import Path

PATH = Path(__file__).with_name("install_unity_evidence_whitespace_hygiene.py")
OLD = "        '''#!/usr/bin/env python3"
NEW = "        r'''#!/usr/bin/env python3"


def main() -> int:
    text = PATH.read_text(encoding="utf-8")
    count = text.count(OLD)
    if count != 2:
        raise SystemExit(f"expected exactly two generated Python templates, found {count}")
    PATH.write_text(text.replace(OLD, NEW), encoding="utf-8", newline="\n")
    print("Repaired two generated Python templates to preserve escape sequences.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
