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

# GUIDS UNITY SHIPS, WHICH NO .meta UNDER Assets/ CAN EVER DECLARE, each with what it is and how it
# was read. The known-guid index is built from Assets/**/*.meta, so a reference into a PACKAGE
# (Library/PackageCache, deliberately excluded above as build output) or into Unity's own built-in
# resource bundles looks exactly like a typo to the checks below. Measured 2026-09-26 on the first
# prefab to carry a uGUI Image: eight FAILs, every one of them a Unity-shipped guid. A declared
# table, never a blanket skip - an unknown package guid still fails, which is the point.
UNITY_BUILTIN_EXTRA_GUID = "0000000000000000f000000000000000"

# A uGUI Image with NO sprite is a solid quad in its colour - the HUD's title panels and debug
# buttons are exactly that, as the scene builder made them - so "renders nothing" is false for it
# and only for it. The allowance is scoped to the one document class that has that semantics: a
# SpriteRenderer pointing at fileID 0 still fails. Read from com.unity.ugui's own Image.cs.meta.
UGUI_IMAGE_SCRIPT_GUID = "fe87c0e1cc204ed48ad3b37840f39efc"

UNITY_SHIPPED_GUIDS = {
    UNITY_BUILTIN_EXTRA_GUID:
        "unity_builtin_extra: Sprites-Default (10754), the Standard shader (46) and the UI/Skin "
        "sprites UISprite.psd (10905) and Background.psd (10907). These sprites are not sub-assets "
        "of a texture, so their fileIDs are legitimately not 21300000.",
    "fe87c0e1cc204ed48ad3b37840f39efc":
        "com.unity.ugui Runtime/UGUI/UI/Core/Image.cs, read from the package cache's own .meta. "
        "DoorBreachFeedback.durabilityFill is typed Image, so a door prefab must reference it.",
    "0cd44c1031e13a943bb63640046fad76":
        "com.unity.ugui Runtime/UGUI/UI/Core/Layout/CanvasScaler.cs, read from the package cache.",
    "dc42784cf147c0c48a680349fa168899":
        "com.unity.ugui Runtime/UGUI/UI/Core/GraphicRaycaster.cs, read from the package cache.",
}

GUID_PATTERN = re.compile(r"guid:\s*([0-9a-f]{32})\b")
SPRITE_PATTERN = re.compile(r"m_Sprite:\s*\{fileID:\s*(-?\d+)(?:,\s*guid:\s*([0-9a-f]{32}))?")
SCRIPT_PATTERN = re.compile(r"m_Script:\s*\{fileID:\s*(-?\d+),\s*guid:\s*([0-9a-f]{32})")
ANCHOR_PATTERN = re.compile(r"^--- !u!(\d+) &(-?\d+)", re.MULTILINE)


def documents(text: str):
    """(is_ugui_image, document_text) for every YAML document in the file, in order.

    The sprite rule needs to know WHICH component a sprite reference sits on, and a whole-file regex
    cannot tell an Image's m_Sprite from a SpriteRenderer's. A document is class 114 carrying the
    uGUI Image script, or it is something else; nothing finer than that is decided here.
    """
    anchors = list(ANCHOR_PATTERN.finditer(text))
    for index, anchor in enumerate(anchors):
        end = anchors[index + 1].start() if index + 1 < len(anchors) else len(text)
        document = text[anchor.start():end]
        script = SCRIPT_PATTERN.search(document)
        is_ugui_image = (anchor.group(1) == "114" and script is not None
                         and script.group(2) == UGUI_IMAGE_SCRIPT_GUID)
        yield is_ugui_image, document


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
    for is_ugui_image, document in documents(text):
        for file_id, guid in SPRITE_PATTERN.findall(document):
            if file_id == "0":
                if is_ugui_image:
                    # A uGUI Image with no sprite draws a solid quad in its colour. Not "nothing".
                    continue
                saw_unassigned_sprite = True
                if sprite_optional_reason is None:
                    failures.append("has an m_Sprite pointing at fileID 0, which renders nothing")
            elif file_id != SPRITE_SUBASSET_FILE_ID and guid != UNITY_BUILTIN_EXTRA_GUID:
                # A built-in UI/Skin sprite is the one legitimate non-21300000 sprite reference;
                # any other fileID is still a broken reference (see UNITY_SHIPPED_GUIDS).
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


def collect_package_guids(project_root: pathlib.Path) -> dict:
    """Every guid declared by a .meta in the resolved package cache.

    THIS IS THE ROOT FIX FOR A HOLE THREE LANES WORKED AROUND SEPARATELY. The Assets index cannot
    contain a package guid - packages live under Library/PackageCache, outside Assets by
    construction - so any prefab referencing a package component failed the reference check. The
    door lane hit it on uGUI's Image, the player and enemies lanes both hit it on
    NavMeshModifier, and each one was told to route around it. Three workarounds for one missing
    directory.

    An ALLOWLIST would have been the third wrong answer: it grows forever, every entry is a
    hand-copied 32-hex string nobody re-verifies, and it is wrong the moment a package updates.
    Reading the cache is the same check the Assets index performs, pointed at the other place
    Unity keeps assets.

    Returns guid -> a single synthetic owner, because two PACKAGES sharing a guid is not a defect
    this project can cause or fix; only duplicate claims inside Assets are ours.
    """
    cache = project_root / "Library" / "PackageCache"
    if not cache.is_dir():
        return {}

    guids = {}
    for meta in cache.rglob("*.meta"):
        match = GUID_PATTERN.search(meta.read_bytes().decode("utf-8", errors="replace"))
        if match:
            guids.setdefault(match.group(1), ["<package>"])
    return guids


def collect_guid_owners(root: pathlib.Path) -> dict:
    """Every guid any .meta declares, mapped to the file(s) that declare it.

    A CONTROL, NOT A CONVENIENCE: without it the reference checks silently pass on a typo, because
    an unresolvable guid looks exactly like a resolvable one in text.

    AND IT IS A DICT RATHER THAN A SET FOR A MEASURED REASON. The first version of this function
    built a set, and an adversarial review pointed out what that costs: two files claiming the SAME
    guid do not collide in a set, they DEDUPE - so the one failure that parallel authoring actually
    produces was the one failure this tool could not see. Unity resolves a duplicated guid by
    picking one file arbitrarily and the other asset silently stops existing.
    """
    # Seeded with Unity's own shipped guids, each under a synthetic owner rather than a real path.
    # TWO INDEPENDENT FIXES MEET HERE AND BOTH ARE KEPT:
    #   - the dict (rather than a set) so a DUPLICATE guid fails instead of silently deduping;
    #   - the shipped guids so a prefab referencing a PACKAGE component can pass at all. The index
    #     is Assets/**/*.meta, which structurally CANNOT contain a package or builtin guid, so
    #     before this every door prefab failed on `Image` - 8 FAILs, none of them real.
    # The synthetic owner is what keeps them from reading as two project files claiming one guid.
    owners = {guid: ["<unity-shipped>"] for guid in UNITY_SHIPPED_GUIDS}
    for meta in root.rglob("*.meta"):
        if "Library" in meta.parts or "Temp" in meta.parts:
            continue
        match = GUID_PATTERN.search(meta.read_bytes().decode("utf-8", errors="replace"))
        if match:
            owners.setdefault(match.group(1), []).append(meta.as_posix())
    return owners


def report_duplicate_guids(owners: dict) -> int:
    """Prints every guid claimed by more than one .meta. Returns how many were found.

    THIS IS THE CHECK THAT MATTERS WHEN SEVEN WORKERS AUTHOR YAML IN PARALLEL. Each derives its
    guids deterministically and each checks against the guids that existed when it STARTED, so two
    lanes adding a file at the same relative path - or two deterministic derivations that happen to
    collide - are invisible from inside either branch. Only the merged tree shows it.
    """
    duplicates = 0
    for guid, paths in sorted(owners.items()):
        if len(paths) > 1:
            duplicates += 1
            print("FAIL guid {0} is claimed by {1} files:".format(guid, len(paths)))
            for path in sorted(paths):
                print("       " + path)
    return duplicates


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

    guid_owners = {} if arguments.skip_guid_resolution else collect_guid_owners(assets)

    # Duplicate detection runs over the ASSETS index only - see collect_package_guids for why -
    # so the package guids are merged into the known set AFTER that dict is built, and the two
    # counts are reported separately rather than as one number that hides which is which.
    package_guids = {} if arguments.skip_guid_resolution else collect_package_guids(
        assets.parent if assets.name == "Assets" else pathlib.Path("."))
    known_guids = set(guid_owners) | set(package_guids)

    # Duplicates first: a collision makes every OTHER finding about those files unreliable, because
    # the reference that resolves may not resolve to the file you are reading.
    duplicate_guids = report_duplicate_guids(guid_owners)

    failed = 0
    for prefab in prefabs:
        failures = check_prefab(prefab, known_guids)
        if failures:
            failed += 1
            for failure in failures:
                print("FAIL {0}: {1}".format(prefab.as_posix(), failure))

    print("prefab_lint: {0} prefab(s) checked, {1} with failures, {2} project guid(s) + "
          "{3} package guid(s) indexed, {4} duplicated.".format(
              len(prefabs), failed, len(guid_owners), len(package_guids), duplicate_guids))
    return 1 if (failed or duplicate_guids) else 0


if __name__ == "__main__":
    sys.exit(main())
