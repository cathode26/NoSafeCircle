#!/usr/bin/env python3
"""Static checks for the authoritative DoorPrototype Unity scene location."""

from pathlib import Path, PurePosixPath
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
SCENE_PATH = "Assets/Scenes/DoorPrototype.unity"
META_PATH = SCENE_PATH + ".meta"
EXPECTED_GUID = "92dbd0a3e6c18e245896a66c5120379d"
OBSOLETE_DIRECTORY = Path("Assets/NoSafeCircle/DoorPrototype/Scenes")
BUILDER_PATH = Path("Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs")
CAMERA_FIXTURES = (
    Path("Assets/NoSafeCircle/DoorPrototype/Tests/Editor/DoorPrototypeSceneBuilderTests.cs"),
    Path("Assets/NoSafeCircle/DoorPrototype/Tests/Editor/CommittedSceneCameraConformanceTests.cs"),
)


def read(relative_path: Path | str) -> str:
    path = ROOT / relative_path
    if not path.is_file():
        raise AssertionError(f"Required file does not exist: {relative_path}")
    return path.read_text(encoding="utf-8-sig")


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [path.decode("utf-8") for path in result.stdout.split(b"\0") if path]


def main() -> int:
    tracked = tracked_files()
    tracked_scenes = [path for path in tracked if PurePosixPath(path).name == "DoorPrototype.unity"]
    if tracked_scenes != [SCENE_PATH]:
        raise AssertionError(
            f"Expected exactly one tracked DoorPrototype.unity at {SCENE_PATH}; found {tracked_scenes}"
        )

    if not (ROOT / SCENE_PATH).is_file():
        raise AssertionError(f"Authoritative scene does not exist: {SCENE_PATH}")

    meta = read(META_PATH)
    guid_match = re.search(r"(?m)^guid:\s*([0-9a-fA-F]+)\s*$", meta)
    if guid_match is None or guid_match.group(1) != EXPECTED_GUID:
        actual = guid_match.group(1) if guid_match else "missing"
        raise AssertionError(f"Expected {META_PATH} GUID {EXPECTED_GUID}; found {actual}")

    obsolete_paths = (
        OBSOLETE_DIRECTORY / "DoorPrototype.unity",
        OBSOLETE_DIRECTORY / "DoorPrototype.unity.meta",
        Path(str(OBSOLETE_DIRECTORY) + ".meta"),
    )
    for obsolete_path in obsolete_paths:
        if (ROOT / obsolete_path).exists():
            raise AssertionError(f"Obsolete Unity asset path still exists: {obsolete_path}")

    builder = read(BUILDER_PATH)
    if not re.search(r'private const string SceneFolder\s*=\s*"Assets/Scenes"\s*;', builder):
        raise AssertionError("Production scene builder does not use Assets/Scenes")
    if not re.search(r'ScenePath\s*=\s*SceneFolder\s*\+\s*"/DoorPrototype\.unity"', builder):
        raise AssertionError("Production scene builder does not build DoorPrototype.unity in SceneFolder")

    for fixture_path in CAMERA_FIXTURES:
        fixture = read(fixture_path)
        if SCENE_PATH not in fixture:
            raise AssertionError(f"Camera test fixture does not use {SCENE_PATH}: {fixture_path}")

    obsolete_scene_path = (OBSOLETE_DIRECTORY / "DoorPrototype.unity").as_posix()
    active_files = [
        path for path in (ROOT / "Assets").rglob("*.cs")
        if path.is_file()
    ]
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in active_files
        if obsolete_scene_path in path.read_text(encoding="utf-8-sig")
    ]
    if offenders:
        raise AssertionError(f"Active production/test files reference obsolete scene path: {offenders}")

    print("PASS: DoorPrototype scene location and Unity asset identity are authoritative.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, subprocess.CalledProcessError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
