#!/usr/bin/env python3
"""Make the generated helper template raw while keeping its test template escaped."""

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
    # The helper template contains single-backslash byte literals such as b"\\r\\n"
    # and must be raw. The smoke-test template intentionally contains doubled
    # backslashes and must remain a normal string so it generates ordinary Python
    # byte literals rather than literal backslash characters.
    PATH.write_text(text.replace(OLD, NEW, 1), encoding="utf-8", newline="\n")
    print("Repaired the generated helper template while preserving test escapes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
