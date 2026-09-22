"""Deterministically materialize Door Prototype Unity assets from reviewed C#.

This module owns the Unity batch-mode boundary shared by production candidate
integration and the conversation-operated AssistantControl workflow.  It does
not commit, approve, integrate, push, or launch a model provider.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
import hashlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Sequence


DOOR_PROTOTYPE_BUILDER = (
    "Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs"
)
DOOR_PROTOTYPE_ROOT = "Assets/NoSafeCircle/DoorPrototype/"
DOOR_PROTOTYPE_SCENE = "Assets/Scenes/DoorPrototype.unity"
DOOR_PROTOTYPE_BUILD_METHOD = (
    "NoSafeCircle.DoorPrototype.Editor.DoorPrototypeSceneBuilder.Build"
)
NSC032_INCIDENTAL_FOLDER_META = (
    "Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies.meta"
)


@dataclass(frozen=True)
class RoomSceneBuilder:
    """One exact room scene's deterministic Unity builder entry point."""

    scene_path: str
    build_method: str
    builder_source_path: str


# Exact, reviewable registry of the five approved room scenes. There is
# deliberately no wildcard match for an arbitrary file under
# ``Assets/Scenes/Rooms/``.
#
# EACH ROOM NAMES ITS OWN ENTRY POINT AND THEY ARE NOT ALL CALLED ``Build``.
# This comment used to say every room defined a static ``Build``. That was
# true of RuinedEntry, which existed on 2026-09-12 when this table was being
# written, and false of the four rooms that landed on 2026-09-13 naming their
# entry point ``BuildAndSave``. Unity then failed materialization with
# "method 'Build' ... could not be found" and ZERO compiler errors -- the
# candidate compiles; the entry point simply does not exist. Three
# review-ready room candidates were blocked by it on 2026-09-22.
#
# ``Build`` and ``BuildAndSave`` are one ROLE under two names, not two
# methods: in every builder the ``[MenuItem]``-decorated method is the one
# that builds AND saves, and every builder also has ``BuildInMemoryForTests``
# which must never be registered here -- it does not save.
#
# ``test_registry_names_entry_points_that_exist_in_the_builder_source``
# reads the C# and fails if an entry here names a method that is not there.
# Before it, the only check compared this table against a constant in the
# test file holding the same assumption, so it could never fail.
ROOM_SCENE_BUILDERS: dict[str, RoomSceneBuilder] = {
    "Assets/Scenes/Rooms/RuinedEntry.unity": RoomSceneBuilder(
        scene_path="Assets/Scenes/Rooms/RuinedEntry.unity",
        build_method="NoSafeCircle.DoorPrototype.Editor.Rooms.RuinedEntrySceneBuilder.Build",
        builder_source_path=(
            "Assets/NoSafeCircle/DoorPrototype/Editor/Rooms/RuinedEntrySceneBuilder.cs"
        ),
    ),
    "Assets/Scenes/Rooms/BoneArchive.unity": RoomSceneBuilder(
        scene_path="Assets/Scenes/Rooms/BoneArchive.unity",
        build_method="NoSafeCircle.DoorPrototype.Editor.Rooms.BoneArchiveSceneBuilder.BuildAndSave",
        builder_source_path=(
            "Assets/NoSafeCircle/DoorPrototype/Editor/Rooms/BoneArchiveSceneBuilder.cs"
        ),
    ),
    "Assets/Scenes/Rooms/ChapelOfAsh.unity": RoomSceneBuilder(
        scene_path="Assets/Scenes/Rooms/ChapelOfAsh.unity",
        build_method="NoSafeCircle.DoorPrototype.Editor.Rooms.ChapelOfAshSceneBuilder.BuildAndSave",
        builder_source_path=(
            "Assets/NoSafeCircle/DoorPrototype/Editor/Rooms/ChapelOfAshSceneBuilder.cs"
        ),
    ),
    "Assets/Scenes/Rooms/LowerVault.unity": RoomSceneBuilder(
        scene_path="Assets/Scenes/Rooms/LowerVault.unity",
        build_method="NoSafeCircle.DoorPrototype.Editor.Rooms.LowerVaultSceneBuilder.BuildAndSave",
        builder_source_path=(
            "Assets/NoSafeCircle/DoorPrototype/Editor/Rooms/LowerVaultSceneBuilder.cs"
        ),
    ),
    "Assets/Scenes/Rooms/FinalRoom.unity": RoomSceneBuilder(
        scene_path="Assets/Scenes/Rooms/FinalRoom.unity",
        build_method="NoSafeCircle.DoorPrototype.Editor.Rooms.FinalRoomSceneBuilder.BuildAndSave",
        builder_source_path=(
            "Assets/NoSafeCircle/DoorPrototype/Editor/Rooms/FinalRoomSceneBuilder.cs"
        ),
    ),
}
UNITY_SERIALIZED_SUFFIXES = (
    ".asset", ".unity", ".prefab", ".mat", ".meta", ".anim", ".controller",
    ".overrideController", ".physicsMaterial2D", ".spriteatlas", ".preset",
    ".renderTexture", ".playable", ".signal", ".mask", ".guiskin", ".fontsettings",
)

_UNITY_VERSION = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]*$")
UnityCommandRunner = Callable[
    [Sequence[str], Path, float], subprocess.CompletedProcess[bytes]
]


class DoorPrototypeMaterializationError(RuntimeError):
    """Unity materialization could not be authenticated or completed."""


@dataclass(frozen=True)
class DoorPrototypeMaterialization:
    changed_paths: tuple[str, ...]
    builder_paths: tuple[str, ...]
    restored_tracked_paths: tuple[str, ...]
    normalized_paths: tuple[str, ...]
    authenticated_incidental_meta_paths: tuple[str, ...]
    generated_asset_meta_paths: tuple[str, ...]
    generated_folder_meta_paths: tuple[str, ...]
    incidental_evidence_path: str | None
    unity_executable: str
    unity_log: str


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    try:
        result = subprocess.run(
            ("git", "-C", str(root), *args),
            cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False, timeout=600,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DoorPrototypeMaterializationError(
            "materialization Git command could not run: " + " ".join(args)
        ) from exc
    if check and result.returncode:
        detail = _decode(result.stderr or result.stdout, "Git output").strip()
        raise DoorPrototypeMaterializationError(
            "materialization Git command failed: " + " ".join(args)
            + (f"\n{detail}" if detail else "")
        )
    return result


def _decode(value: bytes, label: str) -> str:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DoorPrototypeMaterializationError(f"{label} was not valid UTF-8") from exc


def _git_lines(root: Path, *args: str) -> tuple[str, ...]:
    output = _decode(_git(root, *args).stdout, "Git output")
    return tuple(sorted((line for line in output.splitlines() if line), key=str.casefold))


def _status_paths(root: Path) -> tuple[tuple[str, str], ...]:
    """Every path git reports as not-clean, with its XY status code.

    Uses the EXACT command authoritative validation uses, because the two must
    agree. `git diff --name-only HEAD` does not: a file whose only difference
    is line endings normalizes away under diff and still reports ` M` under
    status. Measured on NSC-046, where Unity rewrote a settings file with LF,
    the bytes were provably identical, and the boundary could not see what
    validation then refused.
    """
    output = _decode(
        _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout,
        "Git status",
    )
    records = [item for item in output.split("\0") if item]
    entries: list[tuple[str, str]] = []
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if len(record) < 4:
            continue
        code, path = record[:2], record[3:]
        entries.append((code, path))
        if code[0] in {"R", "C"} or code[1] in {"R", "C"}:
            # A rename or copy carries its SOURCE as the next NUL record. The
            # source is a change too, and skipping it here would silently drop
            # a path from the boundary.
            if index < len(records):
                entries.append((code, records[index]))
                index += 1
    return tuple(entries)


def changed_paths(root: Path) -> tuple[str, ...]:
    return tuple(sorted({path for _code, path in _status_paths(root)},
                        key=str.casefold))


def tracked_changed_paths(root: Path) -> tuple[str, ...]:
    """Not-clean paths that git already tracks, so they can be restored."""
    return tuple(sorted(
        {path for code, path in _status_paths(root) if code != "??"},
        key=str.casefold,
    ))


def untracked_paths(root: Path) -> tuple[str, ...]:
    return tuple(sorted(
        {path for code, path in _status_paths(root) if code == "??"},
        key=str.casefold,
    ))


def is_expected_nsc032_folder_meta(root: Path, path: str, content: bytes) -> bool:
    """Recognize only Unity's meta for the committed Enemies folder."""
    if path != NSC032_INCIDENTAL_FOLDER_META or len(content) > 4096:
        return False
    folder = path[:-len(".meta")]
    lines = content.decode("utf-8-sig", errors="replace").splitlines()
    return bool(
        len(lines) >= 4
        and lines[0] == "fileFormatVersion: 2"
        and re.fullmatch(r"guid: [0-9a-f]{32}", lines[1])
        and lines[2] == "folderAsset: yes"
        and lines[3] == "DefaultImporter:"
        and not _git(root, "cat-file", "-e", f"HEAD:{folder}/.gitkeep", check=False).returncode
        and _git(root, "cat-file", "-e", f"HEAD:{path}", check=False).returncode
    )


ASSET_META_MAX_BYTES = 1 << 20


def _asset_meta_guid(content: bytes) -> str:
    """Return the guid of a plain asset meta, or "" if it is not one.

    An ENVELOPE check, deliberately not a YAML or importer-settings validator:
    the importer body is builder output that Unity and human review own. What
    is checked is identity -- one version line, one 32-hex guid, one top-level
    "<Name>Importer:" key -- and that nothing else is declared at top level.

    The folder-meta policy's grammar does NOT apply here and neither does its
    4096-byte cap: a real asset meta carries importer settings.
    """
    if len(content) > ASSET_META_MAX_BYTES:
        return ""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return ""
    if "\r" in text.replace(chr(13) + chr(10), ""):
        return ""
    lines = text.replace(chr(13) + chr(10), "\n").split("\n")
    if len(lines) < 3 or lines[0] != "fileFormatVersion: 2":
        return ""
    guid_match = re.fullmatch(r"guid: ([0-9a-fA-F]{32})", lines[1])
    if not guid_match:
        return ""
    guid = guid_match.group(1).casefold()
    if guid == "0" * 32:
        return ""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*Importer:", lines[2]):
        return ""
    for line in lines[3:]:
        if line and not line[0].isspace():
            # A second top-level declaration means this is not a plain meta.
            return ""
        if line.casefold().strip() == "folderasset: yes":
            return ""
    return guid


def _folder_meta_guid(content: bytes) -> str:
    """Return the guid of a plain FOLDER meta, or "" if it is not one.

    Deliberately separate from the asset-meta envelope: a folder meta has no
    importer settings, so it can be held to a complete grammar rather than an
    envelope. The two predicates must never fall back to each other -- an asset
    meta admitted as a folder repair, or the reverse, would be a real authority
    leak.
    """
    if len(content) > 4096:
        return ""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return ""
    lines = text.replace(chr(13) + chr(10), "\n").split("\n")
    if len(lines) < 4 or lines[0] != "fileFormatVersion: 2":
        return ""
    guid_match = re.fullmatch(r"guid: ([0-9a-fA-F]{32})", lines[1])
    if not guid_match:
        return ""
    guid = guid_match.group(1).casefold()
    if guid == "0" * 32:
        return ""
    if lines[2] != "folderAsset: yes" or lines[3] != "DefaultImporter:":
        return ""
    for line in lines[4:]:
        if line and not line[0].isspace():
            return ""
    return guid


def _authenticate_folder_metas(
    root: Path, admitted: Sequence[str], inventory: Sequence[str],
) -> tuple[str, ...]:
    """Accept only pinned, genuinely missing metas for committed folders."""
    pinned = set(inventory)
    seen: dict[str, str] = {}
    accepted: list[str] = []
    for meta in admitted:
        if meta not in pinned:
            # Defence in depth; this cannot normally be reached, because the
            # caller already filters the admitted list to inventory members.
            # The REAL protection for a meta outside the inventory is the
            # incidental_untracked refusal below. Found by mutation.
            raise DoorPrototypeMaterializationError(
                f"folder_meta_not_in_inventory: {meta}")
        folder = meta[: -len(".meta")]
        if not folder.startswith(DOOR_PROTOTYPE_ROOT):
            raise DoorPrototypeMaterializationError(
                f"folder_meta_outside_root: {meta}")
        target = root / meta
        if not target.is_file() or target.is_symlink():
            raise DoorPrototypeMaterializationError(
                f"folder_meta_not_regular: {meta}")
        if not (root / folder).is_dir():
            raise DoorPrototypeMaterializationError(
                f"folder_meta_has_no_directory: {meta}")
        if not _git(root, "cat-file", "-e", f"HEAD:{meta}", check=False).returncode:
            raise DoorPrototypeMaterializationError(
                f"folder_meta_preexists: {meta}")
        try:
            content = target.read_bytes()
        except OSError as exc:
            raise DoorPrototypeMaterializationError(
                f"folder_meta_unreadable: {meta}") from exc
        guid = _folder_meta_guid(content)
        if not guid:
            raise DoorPrototypeMaterializationError(
                f"folder_meta_invalid_content: {meta}")
        if guid in seen:
            raise DoorPrototypeMaterializationError(
                f"folder_meta_guid_collision: {meta} and {seen[guid]}")
        seen[guid] = meta
        accepted.append(meta)
    return tuple(sorted(accepted, key=str.casefold))


def _authenticate_asset_metas(
    root: Path, admitted: Sequence[str], allowed: Sequence[str],
) -> tuple[str, ...]:
    """Accept only new companions that pair with a registered payload."""
    payloads = set(allowed)
    seen_guids: dict[str, str] = {}
    accepted: list[str] = []
    for meta in admitted:
        payload = meta[: -len(".meta")]
        if payload not in payloads:
            raise DoorPrototypeMaterializationError(
                f"asset_meta_not_registered: {meta}"
            )
        if not (root / payload).is_file():
            raise DoorPrototypeMaterializationError(
                f"asset_meta_payload_missing: {meta}"
            )
        target = root / meta
        if not target.is_file() or target.is_symlink():
            raise DoorPrototypeMaterializationError(
                f"asset_meta_not_regular: {meta}"
            )
        if not _git(root, "cat-file", "-e", f"HEAD:{meta}", check=False).returncode:
            # Defence in depth: the pre-launch check above is what actually
            # fires. This one cannot normally be reached, because a committed
            # meta arrives as a TRACKED change and never enters this list.
            raise DoorPrototypeMaterializationError(
                f"asset_meta_preexists: {meta}"
            )
        try:
            content = target.read_bytes()
        except OSError as exc:
            raise DoorPrototypeMaterializationError(
                f"asset_meta_unreadable: {meta}"
            ) from exc
        guid = _asset_meta_guid(content)
        if not guid:
            raise DoorPrototypeMaterializationError(
                f"asset_meta_invalid_envelope: {meta}"
            )
        if guid in seen_guids:
            raise DoorPrototypeMaterializationError(
                f"asset_meta_guid_collision: {meta} and {seen_guids[guid]}"
            )
        seen_guids[guid] = meta
        accepted.append(meta)
    return tuple(sorted(accepted, key=str.casefold))


def is_door_prototype_builder_output(path: str) -> bool:
    return (
        path.startswith(DOOR_PROTOTYPE_ROOT)
        or path == DOOR_PROTOTYPE_SCENE
        or path in ROOM_SCENE_BUILDERS
    )


def resolve_generated_builder(paths: Sequence[str]) -> tuple[str, str]:
    """Return the single ``(build_method, builder_source_path)`` that owns every path.

    Raises when a path is not a registered Unity builder output, or when the
    given paths genuinely span more than one builder; materialization must
    invoke exactly one exact static entry point per request -- whatever that
    room names it.

    A request naming exactly ONE registered room scene absorbs the generated
    DoorPrototype outputs in the same request, because they are that room
    build's own products. The registry is keyed by scene path, so a room's
    generated tiles otherwise fall through to the module default and make a
    single-room request look like a two-builder one. That blocked NSC-044,
    NSC-046 and NSC-047 on 2026-09-22, and NSC-044 tripped it with
    ``new_implementation_paths == []`` from an asset it merely OWNS -- so the
    trigger was never "the task creates a tile".

    Resolved here rather than by registering each generated path, because the
    builders declare their output constants in the CANDIDATE:
    ``ChapelOfAshSceneBuilder`` on main has no tile code at all, and only
    RuinedEntry's is witnessable today. A static table would have to carry
    entries main cannot verify or omit the ones it cannot see -- which is the
    defect this module produced once already.

    Unchanged on purpose: two room scenes still refuse, generated paths with no
    room scene still use the module default, an unregistered path outside the
    DoorPrototype root is still refused, and a request naming the composed
    ``DoorPrototype.unity`` scene still refuses alongside a room, because that
    scene is the default builder's own output rather than a room's.
    """
    rooms: set[tuple[str, str]] = set()
    prototype_owned: list[str] = []
    for path in paths:
        room = ROOM_SCENE_BUILDERS.get(path)
        if room is not None:
            rooms.add((room.build_method, room.builder_source_path))
        elif path.startswith(DOOR_PROTOTYPE_ROOT) or path == DOOR_PROTOTYPE_SCENE:
            prototype_owned.append(path)
        else:
            raise DoorPrototypeMaterializationError(
                f"path is not a registered Unity builder output: {path}"
            )

    owners: set[tuple[str, str]] = set(rooms)
    absorbed_by_room = (
        len(rooms) == 1 and DOOR_PROTOTYPE_SCENE not in prototype_owned
    )
    if prototype_owned and not absorbed_by_room:
        # With no room, with two rooms, or when the composed prototype scene is
        # itself in scope, the default builder is a real second builder.
        owners.add((DOOR_PROTOTYPE_BUILD_METHOD, DOOR_PROTOTYPE_BUILDER))
    if not owners:
        raise DoorPrototypeMaterializationError(
            "no generated paths were given to resolve a Unity builder"
        )
    if len(owners) != 1:
        methods = ", ".join(sorted(method for method, _source in owners))
        raise DoorPrototypeMaterializationError(
            f"generated paths require more than one builder method: {methods}"
        )
    return next(iter(owners))


def is_unity_serialized(path: str) -> bool:
    return path.casefold().endswith(tuple(s.casefold() for s in UNITY_SERIALIZED_SUFFIXES))


def normalize_unity_serialized_whitespace(
    root: Path, paths: Sequence[str],
) -> tuple[str, ...]:
    """Strip Unity-authored trailing spaces without changing line endings."""
    rewritten: list[str] = []
    for relative in paths:
        if not is_unity_serialized(relative):
            continue
        target = root / relative
        if not target.is_file():
            continue
        try:
            original = target.read_bytes()
            normalized = re.sub(rb"[ \t]+(?=\r?\n|\Z)", b"", original)
            if normalized != original:
                target.write_bytes(normalized)
                rewritten.append(relative)
        except OSError as exc:
            raise DoorPrototypeMaterializationError(
                f"could not normalize Unity serialized output: {target}"
            ) from exc
    return tuple(rewritten)


def resolve_unity_executable(
    checkout: Path, unity_executable: Path | str | None = None,
) -> Path:
    if unity_executable is not None:
        executable = Path(unity_executable).resolve()
    else:
        version_path = checkout / "ProjectSettings" / "ProjectVersion.txt"
        try:
            version_text = version_path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            raise DoorPrototypeMaterializationError(
                f"could not read Unity version from {version_path}"
            ) from exc
        match = re.search(r"^m_EditorVersion:\s*(\S.*?)\s*$", version_text, re.MULTILINE)
        version = match.group(1) if match else ""
        if not _UNITY_VERSION.fullmatch(version):
            raise DoorPrototypeMaterializationError(
                f"ProjectVersion.txt has an invalid m_EditorVersion value: {version!r}"
            )
        program_files = os.getenv("ProgramFiles")
        if not program_files:
            raise DoorPrototypeMaterializationError(
                "ProgramFiles is unavailable for Unity Hub executable discovery"
            )
        executable = (
            Path(program_files) / "Unity" / "Hub" / "Editor" / version
            / "Editor" / "Unity.exe"
        )
    if not executable.is_file():
        raise DoorPrototypeMaterializationError(
            f"Unity executable does not exist: {executable}"
        )
    return executable


def default_unity_command_runner(
    args: Sequence[str], cwd: Path, timeout_seconds: float,
) -> subprocess.CompletedProcess[bytes]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONUTF8"] = "1"
    return subprocess.run(
        tuple(args), cwd=str(cwd), env=environment, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False, timeout=timeout_seconds,
    )


def run_door_prototype_builder(
    *,
    checkout: Path | str,
    task_id: str,
    state_root: Path | str,
    initial_changed_paths: Sequence[str],
    unity_executable: Path | str | None = None,
    unity_command_runner: UnityCommandRunner = default_unity_command_runner,
    timeout_seconds: float = 1800.0,
    allowed_generated_paths: Sequence[str] | None = None,
    allowed_generated_roots: Sequence[str] | None = None,
    allowed_generated_asset_metas: Sequence[str] | None = None,
    allowed_missing_folder_metas: Sequence[str] | None = None,
    incidental_folder_meta_path: str | None = None,
) -> DoorPrototypeMaterialization:
    """Run the canonical builder and return its exact authenticated path set.

    ``initial_changed_paths`` is the already verified crew patch in production
    and is empty when AssistantControl starts from a committed code candidate.
    Supplying ``allowed_generated_paths`` narrows the normal Door Prototype
    boundary to those exact paths.
    """
    root = Path(checkout).resolve()
    evidence_root = Path(state_root).resolve()
    initial = tuple(sorted(set(initial_changed_paths), key=str.casefold))
    if tuple(initial_changed_paths) != initial:
        raise DoorPrototypeMaterializationError(
            "initial materialization paths must be sorted and unique"
        )
    if timeout_seconds <= 0:
        raise DoorPrototypeMaterializationError("Unity builder timeout must be positive")
    if incidental_folder_meta_path is not None and (
        task_id != "NSC-032"
        or incidental_folder_meta_path != NSC032_INCIDENTAL_FOLDER_META
    ):
        raise DoorPrototypeMaterializationError("incidental folder meta exception is not authorized")
    if changed_paths(root) != initial:
        raise DoorPrototypeMaterializationError(
            "checkout changed after candidate verification and before the DoorPrototype builder"
        )
    allowed = None
    if allowed_generated_paths is not None:
        allowed = tuple(sorted(set(allowed_generated_paths), key=str.casefold))
        if tuple(allowed_generated_paths) != allowed:
            raise DoorPrototypeMaterializationError(
                "allowed generated paths must be sorted and unique"
            )
        if any(not is_door_prototype_builder_output(path) for path in allowed):
            raise DoorPrototypeMaterializationError(
                "allowed generated path is outside the DoorPrototype builder boundary"
            )
    allowed_roots: tuple[str, ...] | None = None
    if allowed_generated_roots is not None:
        allowed_roots = tuple(sorted(set(allowed_generated_roots), key=str.casefold))
        if tuple(allowed_generated_roots) != allowed_roots:
            raise DoorPrototypeMaterializationError(
                "allowed generated roots must be sorted and unique"
            )
        for root_path in allowed_roots:
            parts = PurePosixPath(root_path).parts
            if (
                not root_path.startswith(DOOR_PROTOTYPE_ROOT)
                or root_path == DOOR_PROTOTYPE_ROOT.rstrip("/")
                or root_path.endswith("/")
                or "\\" in root_path
                or any(part in {"", ".", ".."} for part in parts)
            ):
                raise DoorPrototypeMaterializationError(
                    "allowed generated root is outside the DoorPrototype builder boundary"
                )
    if ((allowed_generated_paths is not None or allowed_generated_roots is not None)
            and not allowed and not allowed_roots):
        raise DoorPrototypeMaterializationError(
            "allowed generated authority must contain at least one path or root"
        )

    asset_metas: tuple[str, ...] = ()
    if allowed_generated_asset_metas is not None:
        asset_metas = tuple(sorted(set(allowed_generated_asset_metas), key=str.casefold))
        if tuple(allowed_generated_asset_metas) != asset_metas:
            raise DoorPrototypeMaterializationError(
                "allowed generated asset metas must be sorted and unique"
            )
        for meta in asset_metas:
            if not meta.endswith(".meta") or not meta.startswith("Assets/"):
                raise DoorPrototypeMaterializationError(
                    f"asset_meta_not_registered: {meta}"
                )
            if allowed is None or meta[: -len(".meta")] not in set(allowed):
                raise DoorPrototypeMaterializationError(
                    f"asset_meta_not_registered: {meta}"
                )
            # PRE-LAUNCH eligibility, per Astra's condition 2. This check used
            # to live after Unity ran, behind a filter on the untracked set --
            # where it could NEVER fire, because a committed meta that Unity
            # rewrites appears as a TRACKED change. The outcome was still
            # correct by accident (the tracked branch restores it); the guard
            # asserting it was unreachable. Found by writing the refusal test.
            if not _git(root, "cat-file", "-e", f"HEAD:{meta}", check=False).returncode:
                raise DoorPrototypeMaterializationError(
                    f"asset_meta_preexists: {meta}"
                )

    # Resolved from PAYLOADS ONLY. `allowed` also selects the builder, so a
    # companion reaching this call would fail resolve_generated_builder().
    build_method = DOOR_PROTOTYPE_BUILD_METHOD
    if allowed is not None:
        build_method, _builder_source = resolve_generated_builder(allowed)

    executable = resolve_unity_executable(root, unity_executable)
    evidence_root.mkdir(parents=True, exist_ok=True)
    log_directory = Path(tempfile.mkdtemp(
        prefix=f"{task_id.casefold()}-unity-builder-", dir=evidence_root,
    ))
    log_path = log_directory / "unity.log"
    command = (
        str(executable), "-batchmode", "-quit", "-projectPath", str(root),
        "-executeMethod", build_method, "-logFile", str(log_path),
    )
    ilpp_pid_path = root / "Library" / "ilpp.pid"
    try:
        ilpp_pid_path.unlink(missing_ok=True)
        if os.path.lexists(ilpp_pid_path):
            raise OSError("the path still exists after deletion")
    except OSError as exc:
        raise DoorPrototypeMaterializationError(
            "DoorPrototype builder refused to launch because the stale Unity ILPP "
            f"PID marker could not be removed: {ilpp_pid_path}"
        ) from exc
    try:
        result = unity_command_runner(command, root, timeout_seconds)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DoorPrototypeMaterializationError(
            f"DoorPrototype builder could not run; Unity log: {log_path}"
        ) from exc
    if result.returncode:
        stdout = _decode(result.stdout or b"", "Unity stdout").strip()
        stderr = _decode(result.stderr or b"", "Unity stderr").strip()
        detail = "\n".join(item for item in (stdout, stderr) if item)
        raise DoorPrototypeMaterializationError(
            f"DoorPrototype builder failed ({result.returncode}); Unity log: {log_path}"
            + (f"\n{detail}" if detail else "")
        )

    # Same source of truth as validation, so the boundary can see and restore
    # what validation would otherwise refuse the checkout for.
    tracked = tracked_changed_paths(root)
    untracked = untracked_paths(root)
    initial_set = set(initial)

    def permitted(path: str) -> bool:
        if allowed is None and allowed_roots is None:
            return is_door_prototype_builder_output(path)
        if allowed is not None and path in allowed:
            return True
        if allowed_roots is None or not is_unity_serialized(path):
            return False
        folded = path.casefold()
        return any(folded.startswith(root.casefold() + "/") for root in allowed_roots)

    admitted_asset_metas = _authenticate_asset_metas(
        root, [meta for meta in asset_metas if meta in set(untracked)], allowed or (),
    )
    # The NSC-032 hatch keeps its own path exactly. The general mechanism
    # would subsume it -- Scripts/Enemies is a committed meta-less folder and
    # lands in the inventory -- but that would silently move an existing
    # record's meta from authenticated_incidental_meta_paths to the new field.
    # Changing a live record shape is not part of this fix.
    folder_inventory = tuple(
        meta for meta in (allowed_missing_folder_metas or ())
        if meta != incidental_folder_meta_path
    )
    admitted_folder_metas = _authenticate_folder_metas(
        root, [meta for meta in folder_inventory if meta in set(untracked)],
        folder_inventory,
    )
    admitted_meta_set = set(admitted_asset_metas) | set(admitted_folder_metas)

    incidental_tracked = tuple(
        path for path in tracked if path not in initial_set and not permitted(path)
    )
    if incidental_tracked:
        _git(root, "restore", "--source=HEAD", "--staged", "--worktree", "--",
             *incidental_tracked)
    incidental_untracked = tuple(
        path for path in untracked
        if path not in initial_set and not permitted(path)
        and path not in admitted_meta_set
    )
    authenticated_incidental: tuple[str, ...] = ()
    incidental_evidence_path: str | None = None
    if incidental_folder_meta_path in incidental_untracked:
        path = incidental_folder_meta_path
        meta = root / path
        try:
            content = meta.read_bytes()
        except OSError as exc:
            raise DoorPrototypeMaterializationError("incidental folder meta is unreadable") from exc
        if not is_expected_nsc032_folder_meta(root, path, content):
            raise DoorPrototypeMaterializationError(
                "incidental Enemies.meta is not a generated meta for the committed folder"
            )
        evidence = log_directory / "incidental-Enemies.meta"
        try:
            with evidence.open("xb") as stream:
                stream.write(content)
            if hashlib.sha256(evidence.read_bytes()).digest() != hashlib.sha256(content).digest():
                raise OSError("archived folder meta differs")
            if meta.read_bytes() != content:
                raise OSError("folder meta changed before authentication")
        except OSError as exc:
            raise DoorPrototypeMaterializationError(
                "incidental folder meta could not be preserved and authenticated"
            ) from exc
        authenticated_incidental = (path,)
        incidental_evidence_path = str(evidence)
        incidental_untracked = tuple(item for item in incidental_untracked if item != path)
    if incidental_untracked:
        raise DoorPrototypeMaterializationError(
            "Unity created untracked paths outside the DoorPrototype builder-owned "
            f"boundary: {incidental_untracked}"
        )
    post_unity = set(tracked).union(untracked)
    builder_paths = tuple(sorted(
        (path for path in post_unity.difference(initial_set)
         if permitted(path) or path in authenticated_incidental
         or path in admitted_meta_set),
        key=str.casefold,
    ))
    expected = tuple(sorted(initial_set.union(builder_paths), key=str.casefold))
    remaining = changed_paths(root)
    if remaining != expected:
        raise DoorPrototypeMaterializationError(
            "dirty paths after Unity cleanup differ from candidate plus DoorPrototype "
            f"builder output: {remaining} != {expected}"
        )
    normalized = normalize_unity_serialized_whitespace(root, expected)
    if changed_paths(root) != expected:
        raise DoorPrototypeMaterializationError(
            "Unity output paths changed during serialized whitespace normalization"
        )
    return DoorPrototypeMaterialization(
        changed_paths=expected, builder_paths=builder_paths,
        restored_tracked_paths=incidental_tracked, normalized_paths=normalized,
        authenticated_incidental_meta_paths=authenticated_incidental,
        generated_asset_meta_paths=admitted_asset_metas,
        generated_folder_meta_paths=admitted_folder_metas,
        incidental_evidence_path=incidental_evidence_path,
        unity_executable=str(executable), unity_log=str(log_path),
    )


__all__ = [
    "DOOR_PROTOTYPE_BUILDER", "DOOR_PROTOTYPE_BUILD_METHOD",
    "ROOM_SCENE_BUILDERS", "RoomSceneBuilder",
    "DoorPrototypeMaterialization", "DoorPrototypeMaterializationError",
    "UnityCommandRunner", "changed_paths", "default_unity_command_runner",
    "is_door_prototype_builder_output", "is_unity_serialized",
    "normalize_unity_serialized_whitespace", "resolve_generated_builder",
    "resolve_unity_executable", "run_door_prototype_builder",
    "NSC032_INCIDENTAL_FOLDER_META", "is_expected_nsc032_folder_meta",
]
