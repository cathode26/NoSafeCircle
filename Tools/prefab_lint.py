#!/usr/bin/env python3
"""Check the hand-authored prefab YAML that the new architecture is built from.

WHY THIS EXISTS. Vincent, 2026-09-26: "I write code to instantiate prefabs" / "The scene should just
be some objects that create prefabs." Under that architecture a `.prefab` stops being build output
and becomes a SOURCE FILE that people and agents hand-edit. Source files get linted.

AND WHY IT IS PYTHON RATHER THAN A UNITY TEST. A Unity fixture that opens 45 prefabs costs an
editor launch, a domain reload and minutes; this reads them as text in well under a second, so it
can run on every commit in a branch whose whole point is NOT running the suite every time. It
cannot check anything semantic - that is PropPrefabVerifier's job, inside Unity, where a sprite
reference can actually be resolved. The two are complements, not substitutes:

    prefab_lint.py         the file is well formed, references are shaped right, nothing is a stub
    PropPrefabVerifier     the sprite RESOLVES, the collider is solid, sorting is on the right layer

Exit 0 when everything passes, 1 when anything fails, 2 when the tree itself is wrong (no prefabs
found), which is deliberately distinguishable: a lint that finds nothing to lint has not passed.
"""

import argparse
import pathlib
import re
import sys

# A sprite sub-asset inside a spriteMode:1 texture. Verified across 222 references in Unity's own
# output; an m_Sprite pointing at fileID 0 is an unassigned reference, which imports without
# complaint and renders nothing.
SPRITE_SUBASSET_FILE_ID = "21300000"

# PREFABS ALLOWED TO HAVE AN UNASSIGNED SPRITE, each with the reason it is allowed.
# A DECLARED exception, never a silent skip: an undeclared allowlist is how a real defect hides
# behind a rule somebody added once to make a build green. The inverse is checked too - a prefab
# that is declared sprite-optional and then GAINS a sprite has changed purpose, and that is worth
# noticing rather than quietly passing.
SPRITE_OPTIONAL_BY_DESIGN = {
    "Generated/ArchitecturalTiles/WorldSprites/WorldSpriteVisual.prefab":
        "The TEMPLATE the 45 authored prop prefabs were copied from. It carries the sorting "
        "convention - layer WorldSprites, order 0, SpriteSortPoint Pivot - and deliberately no "
        "sprite, because the sprite is the one thing each copy supplies for itself.",
}

GUID_PATTERN = re.compile(r"guid:\s*([0-9a-f]{32})\b")
SPRITE_PATTERN = re.compile(r"m_Sprite:\s*\{fileID:\s*(-?\d+)(?:,\s*guid:\s*([0-9a-f]{32}))?")
SCRIPT_PATTERN = re.compile(r"m_Script:\s*\{fileID:\s*(-?\d+),\s*guid:\s*([0-9a-f]{32})")
ANCHOR_PATTERN = re.compile(r"^--- !u!(\d+) &(-?\d+)", re.MULTILINE)


def check_prefab(path: pathlib.Path, known_guids: set) -> list:
    """Every failure found in one prefab, as human-readable strings."""
    failures = []
    raw = path.read_bytes()

    # READ AS BYTES AND DECODE EXPLICITLY. Python text mode on Windows decodes with cp1252 and
    # silently mojibakes every non-ASCII character - one em dash becomes three - while git reports
    # the tree clean throughout, because the corruption is in the reader's copy and not in the repo.
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        return ["is not valid UTF-8 ({0})".format(error)]

    if not text.startswith("%YAML 1.1"):
        failures.append("does not begin with the '%YAML 1.1' header Unity writes")

    if b"\r\n" in raw:
        failures.append("contains CRLF line endings; Unity writes LF and a mixed file re-serializes")

    anchors = ANCHOR_PATTERN.findall(text)
    if not anchors:
        failures.append("declares no YAML objects at all")
        return failures

    anchor_ids = [anchor_id for _, anchor_id in anchors]
    duplicates = sorted({a for a in anchor_ids if anchor_ids.count(a) > 1})
    if duplicates:
        failures.append("reuses fileID anchor(s) {0}; every object needs its own".format(duplicates))

    class_ids = {class_id for class_id, _ in anchors}
    if "1" not in class_ids:
        failures.append("has no GameObject (class 1)")
    if "4" not in class_ids:
        failures.append("has no Transform (class 4); Unity will not import it as a prefab")

    relative = path.as_posix()
    sprite_optional_reason = None
    for suffix, reason in SPRITE_OPTIONAL_BY_DESIGN.items():
        if relative.endswith(suffix):
            sprite_optional_reason = reason

    saw_unassigned_sprite = False
    for file_id, guid in SPRITE_PATTERN.findall(text):
        if file_id == "0":
            saw_unassigned_sprite = True
            if sprite_optional_reason is None:
                failures.append("has an m_Sprite pointing at fileID 0, which renders nothing")
        elif file_id != SPRITE_SUBASSET_FILE_ID:
            failures.append(
                "has an m_Sprite with fileID {0}; a sprite sub-asset is {1}".format(
                    file_id, SPRITE_SUBASSET_FILE_ID))
        if guid and known_guids and guid not in known_guids:
            failures.append(
                "references sprite guid {0}, which no .meta in the project declares".format(guid))

    # THE INVERSE GUARD. A declared exception that has quietly stopped applying is a stale rule, and
    # a stale rule is worse than none because it reads as considered.
    if sprite_optional_reason is not None and not saw_unassigned_sprite:
        failures.append(
            "is declared sprite-optional but now assigns a sprite. Remove it from "
            "SPRITE_OPTIONAL_BY_DESIGN, or say why the declaration still holds. Reason on "
            "record: " + sprite_optional_reason)

    for _, guid in SCRIPT_PATTERN.findall(text):
        if known_guids and guid not in known_guids:
            failures.append(
                "references script guid {0}, which no .meta in the project declares".format(guid))

    meta = path.with_suffix(path.suffix + ".meta")
    if not meta.exists():
        failures.append("has no .meta, so Unity generates one and its guid differs per clone")
    elif not GUID_PATTERN.search(meta.read_bytes().decode("utf-8", errors="replace")):
        failures.append("has a .meta with no guid")

    return failures


def collect_known_guids(root: pathlib.Path) -> set:
    """Every guid any .meta in the project declares.

    A CONTROL, NOT A CONVENIENCE: without it the reference checks silently pass on a typo, because
    an unresolvable guid looks exactly like a resolvable one in text.
    """
    guids = set()
    for meta in root.rglob("*.meta"):
        if "Library" in meta.parts or "Temp" in meta.parts:
            continue
        match = GUID_PATTERN.search(meta.read_bytes().decode("utf-8", errors="replace"))
        if match:
            guids.add(match.group(1))
    return guids


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", default="Assets", help="Assets root to scan.")
    parser.add_argument("--subtree", default="", help="Limit to this path under --assets.")
    parser.add_argument("--skip-guid-resolution", action="store_true",
                        help="Skip the guid index (faster, and blind to broken references).")
    arguments = parser.parse_args()

    assets = pathlib.Path(arguments.assets)
    if not assets.is_dir():
        print("FAIL: '{0}' is not a directory. Run this from the Unity project root.".format(assets))
        return 2

    scan_root = assets / arguments.subtree if arguments.subtree else assets
    prefabs = [p for p in sorted(scan_root.rglob("*.prefab"))
               if "Library" not in p.parts and "Temp" not in p.parts]

    if not prefabs:
        # NOT A PASS. An empty result from a wrong path is indistinguishable from a clean tree,
        # which is this workspace's most expensive recurring error.
        print("FAIL: no .prefab files under '{0}'. Nothing was checked.".format(scan_root))
        return 2

    known_guids = set() if arguments.skip_guid_resolution else collect_known_guids(assets)

    failed = 0
    for prefab in prefabs:
        failures = check_prefab(prefab, known_guids)
        if failures:
            failed += 1
            for failure in failures:
                print("FAIL {0}: {1}".format(prefab.as_posix(), failure))

    print("prefab_lint: {0} prefab(s) checked, {1} with failures, {2} guid(s) indexed.".format(
        len(prefabs), failed, len(known_guids)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
