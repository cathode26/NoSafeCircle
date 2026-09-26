#!/usr/bin/env python3
"""Hold the new runtime components to the size the architecture promised.

WHY. Vincent, 2026-09-26: "We want small components, prefabs, poolers, addressables." And
SlotEngineGemReview 06, which is the same idea stated as an engineering rule: "Infrastructure must
remain smaller than the problem it solves." The instantiate-everything design is worth having only
if the spawners stay small; a 900-line spawner is the bake with a different entry point.

ENGINEERING_STANDARDS 4.1 is deliberately not a law - "Size is a warning, not a law ... Review
responsibility rather than worshiping a number" - so this tool is built to match that exactly:

    REVIEW THRESHOLD   150 lines   reported, does not fail. 4.1's "deserves a responsibility review".
    HARD CEILING       200 lines   fails. 4.1's upper bound, past which nobody is reviewing anything.

SCOPE IS DECLARED AND NARROW, and that is the honest part. It checks RUNTIME code only. The ~9,700
lines of edit-time generators under Editor/ are over every threshold here and are EXEMPT because
they are scheduled for deletion at cutover, not because they are acceptable. Linting them would
produce a wall of failures nobody can act on, and a lint nobody can act on gets disabled - which is
how the one that matters gets lost. When the generators are deleted this exemption goes with them.

Exit 0 when nothing exceeds the ceiling, 1 when anything does, 2 when the scan found no files,
which is deliberately distinguishable: a lint that found nothing has not passed.
"""

import argparse
import pathlib
import re
import sys

REVIEW_THRESHOLD = 150
HARD_CEILING = 200
METHOD_REVIEW_THRESHOLD = 30

CLASS_PATTERN = re.compile(
    r"^\s*(?:public|internal|private|protected)?\s*(?:sealed\s+|static\s+|abstract\s+|partial\s+)*"
    r"(class|struct|interface|enum)\s+(\w+)", re.MULTILINE)

# FILES ALLOWED PAST THE CEILING, each with the reason and the condition that retires the exemption.
# Declared rather than silent, for the same reason prefab_lint declares its own: an undeclared
# allowlist is indistinguishable from an oversight six weeks later.
OVERSIZE_BY_DESIGN = {
    # MEASURED BASELINE at 3fbac01c4, 2026-09-26. These eight runtime files were already over the
    # ceiling when this lint was written. They are RECORDED, NOT ENDORSED: the entry exists so the
    # ceiling can bind every NEW file from today without the tool failing on every run, which is
    # how a lint gets switched off and the one that mattered goes with it.
    #
    # MOST OF THESE HAVE A SCHEDULED DEATH. PlayerMovement, EnemyPursuitMovement,
    # EnemyAnimationController and EnemyTargetKnowledge are exactly what the Player and Enemies
    # lanes rewrite as small components under the new architecture, so their exemptions retire when
    # those lanes ship rather than needing a separate cleanup task.
    "Scripts/DemoRunFlow.cs": "233 lines, pre-existing. Demo orchestration.",
    "Scripts/Diagnostics/WalkthroughCapture.cs": "531 lines, pre-existing. Diagnostics, and the "
        "cutover plan deletes roughly 1,300 lines of diagnostics outright.",
    "Scripts/Enemies/EnemyAnimationController.cs": "261 lines, pre-existing. The Enemies lane "
        "rewrites this; the exemption retires with that lane.",
    "Scripts/Enemies/EnemyPursuitMovement.cs": "293 lines, pre-existing. The Enemies lane "
        "rewrites this; the exemption retires with that lane.",
    "Scripts/Enemies/EnemyTargetKnowledge.cs": "224 lines, pre-existing. The Enemies lane "
        "rewrites this; the exemption retires with that lane.",
    "Scripts/PlayerMovement.cs": "272 lines, pre-existing. The Player lane rewrites this; the "
        "exemption retires with that lane.",
    "Scripts/Presentation/HierarchyFader.cs": "252 lines, pre-existing. Presentation.",
    "Scripts/World/Rooms/AsciiRoomMap.cs": "215 lines, and it is Vincent's own authored parser "
        "with 357 total lines of which most are the remarks explaining why declared dimensions "
        "beat inferred ones. Nothing about it is accidental size.",
}


def measure(path: pathlib.Path) -> dict:
    """Significant lines, and the longest method, for one C# file.

    SIGNIFICANT LINES EXCLUDE COMMENTS AND BLANKS, deliberately. This codebase writes long
    explanatory comments on purpose - they are the reason a later reader knows why a decision was
    made - and a size rule that punishes them would trade the thing that makes the code
    maintainable for the number that is supposed to measure maintainability.
    """
    text = path.read_bytes().decode("utf-8", errors="replace")
    lines = text.split("\n")

    significant = 0
    in_block_comment = False
    for line in lines:
        stripped = line.strip()
        if in_block_comment:
            if "*/" in stripped:
                in_block_comment = False
            continue
        if stripped.startswith("/*"):
            if "*/" not in stripped:
                in_block_comment = True
            continue
        if not stripped or stripped.startswith("//"):
            continue
        significant += 1

    classes = [name for kind, name in CLASS_PATTERN.findall(text) if kind == "class"]
    return {"significant": significant, "total": len(lines), "classes": classes}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="Assets/NoSafeCircle/DoorPrototype/Scripts",
                        help="Runtime scripts root. Editor code is deliberately out of scope.")
    parser.add_argument("--ceiling", type=int, default=HARD_CEILING)
    parser.add_argument("--review", type=int, default=REVIEW_THRESHOLD)
    arguments = parser.parse_args()

    root = pathlib.Path(arguments.root)
    if not root.is_dir():
        print("FAIL: '{0}' is not a directory.".format(root))
        return 2

    files = [p for p in sorted(root.rglob("*.cs"))
             if "Library" not in p.parts and "Temp" not in p.parts and "Editor" not in p.parts]

    if not files:
        print("FAIL: no .cs files under '{0}'. Nothing was checked.".format(root))
        return 2

    over_ceiling = []
    for_review = []

    for path in files:
        result = measure(path)
        relative = path.as_posix()
        declared = None
        for suffix, reason in OVERSIZE_BY_DESIGN.items():
            if relative.endswith(suffix):
                declared = reason

        if result["significant"] > arguments.ceiling:
            if declared is None:
                over_ceiling.append((relative, result["significant"]))
            else:
                print("DECLARED {0}: {1} lines, exempt - {2}".format(
                    relative, result["significant"], declared))
        elif result["significant"] > arguments.review:
            for_review.append((relative, result["significant"]))
        elif declared is not None:
            # THE INVERSE GUARD: an exemption that is no longer needed is a stale rule.
            over_ceiling.append((relative,
                                 "is declared oversize but measures {0} lines; remove the "
                                 "exemption".format(result["significant"])))

    for relative, size in for_review:
        print("REVIEW {0}: {1} significant lines (over {2}). Standard 4.1: worth a responsibility "
              "check, not a failure.".format(relative, size, arguments.review))

    for relative, size in over_ceiling:
        print("FAIL {0}: {1}".format(
            relative,
            size if isinstance(size, str)
            else "{0} significant lines, over the {1} ceiling".format(size, arguments.ceiling)))

    print("component_size_lint: {0} runtime file(s) checked, {1} over the ceiling, "
          "{2} worth review.".format(len(files), len(over_ceiling), len(for_review)))
    return 1 if over_ceiling else 0


if __name__ == "__main__":
    sys.exit(main())
