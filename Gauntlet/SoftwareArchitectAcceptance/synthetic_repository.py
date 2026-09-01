"""Deterministic synthetic Unity-shaped Git repository fixture.

The retired Orchestrator Gauntlet modelled *arithmetic* work, which was the
right shape for proving claim contention: two workers either both claimed a
Fibonacci task or they did not. It is the wrong shape for a scheduler whose job
is predicting **integration** conflict, because the expensive failure is not
"two workers claimed the same task", it is "two workers each edited the same
scene".

This module therefore builds a small repository whose change surfaces are
unambiguous and whose Unity hot spots are real files: scenes, prefabs,
ScriptableObject assets and their ``.meta`` companions, plus scripts that are
either clearly isolated or clearly shared.

The generated files are **not valid Unity assets**. They are deterministic text
whose paths and suffixes carry the whole meaning of the fixture. Making them
importable by Unity would add nothing to any scenario in this gauntlet and
would make byte-for-byte determinism harder to prove.

Every write goes through ``resolve_within``, so a manifest-declared path can
never escape the fixture root, and every repository is created beneath a
``FixtureRoot`` this package owns.
"""

from __future__ import annotations

import hashlib
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from acceptance_lib import (
    FIXTURE_IDENTITY_CONFIG_KEY,
    AcceptanceFixtureError,
    FixtureRoot,
    PathContainmentError,
    git_text,
    git_z_paths,
    normalize_observed_paths,
    resolve_within,
    run_git,
    validate_repository_relative_path,
    validate_repository_relative_paths,
    write_contained_text,
)

SOURCE_DIRECTORY_NAME = "source"
CHECKOUTS_DIRECTORY_NAME = "checkouts"
HOOKS_DIRECTORY_NAME = "empty-hooks"
DEFAULT_BRANCH = "main"

FIXTURE_REPOSITORY_IDENTITY = "nsc-fixture://software-architect-acceptance/synthetic-game"
"""This fixture's immutable repository identity.

The synthetic source repository has **no** Git remote on purpose: it must never
resemble something that could be fetched from or pushed to. It still needs a
stable identity so a live-evidence envelope's recorded ``repository`` can be
grounded in the actual checkout instead of being taken on trust, so the builder
writes this value into the repository's own Git configuration.
"""

KIND_CSHARP = "csharp"
KIND_SCENE = "unity_scene"
KIND_PREFAB = "unity_prefab"
KIND_ASSET = "unity_scriptable_object"
KIND_META = "unity_meta"
KIND_TEXT = "text"

SERIALIZED_KINDS = frozenset({KIND_SCENE, KIND_PREFAB, KIND_ASSET})


@dataclass(frozen=True)
class SyntheticFile:
    path: str
    kind: str
    role: str


SYNTHETIC_FILES: tuple[SyntheticFile, ...] = (
    SyntheticFile(
        "SyntheticGame/README.md",
        KIND_TEXT,
        "fixture marker; never a real Unity project",
    ),
    SyntheticFile(
        "SyntheticGame/Scripts/Core/GameManager.cs",
        KIND_CSHARP,
        "central manager; a shared system that serializes work",
    ),
    SyntheticFile(
        "SyntheticGame/Scripts/Enemy/EnemyPursuit.cs",
        KIND_CSHARP,
        "isolated behavior; safe to edit in parallel",
    ),
    SyntheticFile(
        "SyntheticGame/Scripts/Enemy/EnemyTargeting.cs",
        KIND_CSHARP,
        "isolated behavior; safe to edit in parallel",
    ),
    SyntheticFile(
        "SyntheticGame/Scripts/Enemy/RangedEnemyAttack.cs",
        KIND_CSHARP,
        "isolated behavior; safe to edit in parallel",
    ),
    SyntheticFile(
        "SyntheticGame/Scripts/Enemy/EnemyProjectile.cs",
        KIND_CSHARP,
        "isolated behavior; safe to edit in parallel",
    ),
    SyntheticFile(
        "SyntheticGame/Scripts/UI/HudController.cs",
        KIND_CSHARP,
        "UI behavior bound to the HUD prefab",
    ),
    SyntheticFile(
        "SyntheticGame/Scripts/UI/HealthBarView.cs",
        KIND_CSHARP,
        "UI behavior bound to the HUD prefab",
    ),
    SyntheticFile(
        "SyntheticGame/Scripts/Audio/AudioRouter.cs",
        KIND_CSHARP,
        "isolated behavior; safe to edit in parallel",
    ),
    SyntheticFile(
        "SyntheticGame/Prefabs/HUD.prefab",
        KIND_PREFAB,
        "non-merge-safe prefab; the canonical exact-path collision surface",
    ),
    SyntheticFile("SyntheticGame/Prefabs/HUD.prefab.meta", KIND_META, "prefab identity"),
    SyntheticFile(
        "SyntheticGame/Scenes/Game.unity",
        KIND_SCENE,
        "non-merge-safe scene; the human-hold reservation surface",
    ),
    SyntheticFile("SyntheticGame/Scenes/Game.unity.meta", KIND_META, "scene identity"),
    SyntheticFile(
        "SyntheticGame/Scenes/Chapel.unity",
        KIND_SCENE,
        "second non-merge-safe scene; proves scene conflict is per-asset",
    ),
    SyntheticFile("SyntheticGame/Scenes/Chapel.unity.meta", KIND_META, "scene identity"),
    SyntheticFile(
        "SyntheticGame/Data/EnemyTuning.asset",
        KIND_ASSET,
        "ScriptableObject tuning data shared by enemy work",
    ),
    SyntheticFile(
        "SyntheticGame/Data/EnemyTuning.asset.meta",
        KIND_META,
        "asset identity; the .meta companion collision surface",
    ),
    SyntheticFile(
        "SyntheticGame/Data/AudioCatalog.asset",
        KIND_ASSET,
        "ScriptableObject catalog owned by audio work",
    ),
    SyntheticFile(
        "SyntheticGame/Data/AudioCatalog.asset.meta", KIND_META, "asset identity"
    ),
)

SYNTHETIC_FILE_PATHS: tuple[str, ...] = tuple(item.path for item in SYNTHETIC_FILES)
SYNTHETIC_FILES_BY_PATH: Mapping[str, SyntheticFile] = {
    item.path: item for item in SYNTHETIC_FILES
}


def _stable_hex(path: str, salt: str = "") -> str:
    return hashlib.sha256(f"{salt}:{path}".encode("utf-8")).hexdigest()


def _type_name(path: str) -> str:
    return Path(path).stem.replace(".", "")


def initial_content(path: str) -> str:
    """Return the deterministic initial body for one synthetic file."""

    spec = SYNTHETIC_FILES_BY_PATH.get(path)
    if spec is None:
        raise AcceptanceFixtureError(f"unknown synthetic file: {path}")
    guid = _stable_hex(path)[:32]
    name = _type_name(path)
    if spec.kind == KIND_CSHARP:
        namespace = "SyntheticGame." + Path(path).parent.name
        return (
            "// Synthetic acceptance fixture. Not No Safe Circle game code.\n"
            f"namespace {namespace}\n"
            "{\n"
            f"    public sealed class {name}\n"
            "    {\n"
            f"        public const string FixtureId = \"{guid[:16]}\";\n"
            "    }\n"
            "}\n"
        )
    if spec.kind == KIND_META:
        return f"fileFormatVersion: 2\nguid: {guid}\n"
    if spec.kind in SERIALIZED_KINDS:
        return (
            "%YAML 1.1\n"
            "# Synthetic acceptance fixture. Deliberately NOT a valid Unity asset.\n"
            f"--- !u!1 &{int(guid[:8], 16)}\n"
            "SyntheticSerializedAsset:\n"
            f"  m_Name: {name}\n"
            f"  m_Kind: {spec.kind}\n"
            f"  m_FixtureGuid: {guid}\n"
        )
    return (
        "# Synthetic Game Fixture\n"
        "\n"
        "Generated by `Gauntlet/SoftwareArchitectAcceptance/synthetic_repository.py`.\n"
        "This tree is a scheduling test fixture, not a Unity project and not\n"
        "No Safe Circle game content.\n"
    )


def edited_content(path: str, marker: str) -> str:
    """Return the deterministic body for one synthetic file after an edit.

    An edit is an appended, marker-derived line. That is enough to make Git see
    a real content change on an exact path, which is the only property any
    scenario depends on.
    """

    if not marker:
        raise AcceptanceFixtureError("an edit marker must be non-empty")
    digest = _stable_hex(path, salt=marker)[:16]
    spec = SYNTHETIC_FILES_BY_PATH.get(path)
    if spec is None:
        raise AcceptanceFixtureError(f"unknown synthetic file: {path}")
    body = initial_content(path)
    if spec.kind == KIND_CSHARP:
        return body.replace(
            "    }\n}\n",
            f"        public const string Edit{digest[:8]} = \"{digest}\";\n    }}\n}}\n",
        )
    if spec.kind == KIND_META:
        return body + f"# edit:{marker}:{digest}\n"
    if spec.kind in SERIALIZED_KINDS:
        return body + f"  m_Edit{digest[:8]}: {digest}\n"
    return body + f"\nEdit `{marker}` ({digest}).\n"


@dataclass(frozen=True)
class SourceFixture:
    """The synthetic source repository and the fixture root that owns it."""

    fixture_root: FixtureRoot
    root: Path
    hooks_path: Path
    head: str
    tree: str
    repository_identity: str = FIXTURE_REPOSITORY_IDENTITY

    @property
    def checkout_root(self) -> Path:
        return self.fixture_root.path / CHECKOUTS_DIRECTORY_NAME


def _empty_hooks_directory(fixture_root: FixtureRoot) -> Path:
    """Create one guaranteed-empty hooks directory for this fixture.

    A developer's ``core.hooksPath`` or a template directory full of sample
    hooks would otherwise be able to run code during a fixture commit and
    change what the fixture records.
    """

    hooks = fixture_root.path / HOOKS_DIRECTORY_NAME
    hooks.mkdir(parents=True, exist_ok=True)
    for entry in hooks.iterdir():
        raise AcceptanceFixtureError(f"fixture hooks directory is not empty: {entry}")
    return hooks


def _configure_repository(root: Path, hooks_path: Path) -> None:
    """Pin every setting that could otherwise change a generated SHA."""

    settings = (
        # Line-ending or filemode translation would make generated blob SHAs
        # platform dependent, which would silently defeat the determinism proof.
        ("core.autocrlf", "false"),
        ("core.eol", "lf"),
        ("core.filemode", "false"),
        ("core.symlinks", "false"),
        ("core.longpaths", "true"),
        ("core.hooksPath", str(hooks_path)),
        ("core.fsmonitor", "false"),
        ("core.untrackedCache", "false"),
        ("commit.gpgsign", "false"),
        ("tag.gpgsign", "false"),
        ("gc.auto", "0"),
        ("init.defaultBranch", DEFAULT_BRANCH),
        ("user.useConfigOnly", "false"),
        # An identity, deliberately not a remote: nothing in this fixture can be
        # fetched or pushed, but a verifier can still ground a recorded
        # repository claim in the checkout it was handed.
        (FIXTURE_IDENTITY_CONFIG_KEY, FIXTURE_REPOSITORY_IDENTITY),
    )
    for key, value in settings:
        run_git(root, "config", key, value, hooks_path=hooks_path)


def build_source_repository(fixture_root: FixtureRoot) -> SourceFixture:
    """Create the synthetic source repository inside a fixture root we own.

    The resulting commit SHA is reproducible on one host with one Git version:
    identical inputs always produce an identical HEAD.
    """

    if not isinstance(fixture_root, FixtureRoot):
        raise AcceptanceFixtureError(
            "the synthetic repository may only be built inside a FixtureRoot "
            "created by acceptance_lib.create_fixture_root"
        )
    hooks = _empty_hooks_directory(fixture_root)
    root = fixture_root.path / SOURCE_DIRECTORY_NAME
    if root.exists():
        raise AcceptanceFixtureError(f"synthetic source root already exists: {root}")
    root.mkdir(parents=True)
    run_git(
        root,
        "init",
        "--quiet",
        f"--initial-branch={DEFAULT_BRANCH}",
        f"--template={hooks}",
        hooks_path=hooks,
    )
    _configure_repository(root, hooks)
    for spec in SYNTHETIC_FILES:
        write_contained_text(root, spec.path, initial_content(spec.path))
    run_git(root, "add", "--", "SyntheticGame", hooks_path=hooks)
    run_git(
        root,
        "commit",
        "--quiet",
        "-m",
        "Synthetic acceptance fixture: initial game surface",
        commit_index=0,
        hooks_path=hooks,
    )
    head = git_text(root, "rev-parse", "HEAD")
    tree = git_text(root, "rev-parse", "HEAD^{tree}")
    return SourceFixture(
        fixture_root=fixture_root, root=root, hooks_path=hooks, head=head, tree=tree
    )


def create_work_branch(
    source: SourceFixture,
    *,
    branch: str,
    paths: Sequence[str],
    marker: str,
    message: str,
    commit_index: int,
) -> str:
    """Commit an in-flight change on ``branch`` and return its exact SHA.

    The branch is left unmerged so it models durable work that a scheduler must
    treat as an integration reservation.
    """

    declared = validate_repository_relative_paths(paths, where=f"branch {branch}")
    if not declared:
        raise AcceptanceFixtureError(
            f"branch {branch} must change at least one path to be a reservation"
        )
    run_git(
        source.root,
        "checkout",
        "--quiet",
        "-b",
        branch,
        DEFAULT_BRANCH,
        hooks_path=source.hooks_path,
    )
    try:
        for path in declared:
            write_contained_text(source.root, path, edited_content(path, marker))
        run_git(source.root, "add", "--", *declared, hooks_path=source.hooks_path)
        run_git(
            source.root,
            "commit",
            "--quiet",
            "-m",
            message,
            commit_index=commit_index,
            hooks_path=source.hooks_path,
        )
        head = git_text(source.root, "rev-parse", "HEAD")
    finally:
        run_git(
            source.root,
            "checkout",
            "--quiet",
            DEFAULT_BRANCH,
            hooks_path=source.hooks_path,
        )
    return head


def merge_branch_into_main(
    source: SourceFixture, *, branch: str, commit_index: int
) -> str:
    """Integrate ``branch`` so it no longer differs from ``main``.

    This is the deterministic transition scenario F needs: the reservation
    disappears because the work was integrated, not because anything was
    forced.
    """

    run_git(
        source.root, "checkout", "--quiet", DEFAULT_BRANCH, hooks_path=source.hooks_path
    )
    run_git(
        source.root,
        "merge",
        "--quiet",
        "--no-ff",
        "-m",
        f"Integrate {branch}",
        branch,
        commit_index=commit_index,
        hooks_path=source.hooks_path,
    )
    return git_text(source.root, "rev-parse", "HEAD")


def clone_checkout(source: SourceFixture, *, task_id: str, branch: str) -> Path:
    """Create a working checkout of ``branch`` for reservation observation.

    The destination is derived from the fixture root, never supplied by a
    caller, so a checkout cannot be created outside the fixture we own.
    """

    if not str(task_id).replace("-", "").isalnum():
        raise AcceptanceFixtureError(f"unsafe checkout name: {task_id!r}")
    destination = source.checkout_root / str(task_id)
    if destination.exists():
        raise AcceptanceFixtureError(f"checkout already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    run_git(
        source.fixture_root.path,
        "clone",
        "--quiet",
        "--no-hardlinks",
        "--branch",
        branch,
        str(source.root),
        str(destination),
        hooks_path=source.hooks_path,
    )
    _configure_repository(destination, source.hooks_path)
    return destination


def apply_working_tree_edits(
    source: SourceFixture,
    checkout: Path,
    *,
    marker: str,
    tracked_modified: Sequence[str] = (),
    staged: Sequence[str] = (),
    untracked: Sequence[str] = (),
) -> tuple[str, ...]:
    """Create tracked, staged, and untracked changes in a checkout.

    All three categories matter: a scheduler that observed only tracked
    modifications would miss a worker that has already staged a prefab edit or
    dropped a new asset into the tree.
    """

    touched: list[str] = []
    for path in validate_repository_relative_paths(tracked_modified, where="tracked"):
        write_contained_text(checkout, path, edited_content(path, marker))
        touched.append(path)
    for path in validate_repository_relative_paths(staged, where="staged"):
        write_contained_text(checkout, path, edited_content(path, f"{marker}:staged"))
        run_git(checkout, "add", "--", path, hooks_path=source.hooks_path)
        touched.append(path)
    for path in validate_repository_relative_paths(untracked, where="untracked"):
        write_contained_text(
            checkout, path, f"# untracked acceptance fixture artifact for {marker}\n"
        )
        touched.append(path)
    return normalize_observed_paths(touched)


def observe_working_tree_paths(checkout: Path | str) -> tuple[str, ...]:
    """Read tracked, staged, and untracked names from a checkout.

    Names only. The harness never reads file contents to decide a conflict,
    exactly as the scheduler must not.
    """

    paths: list[str] = []
    paths.extend(git_z_paths(checkout, "diff", "--name-only", "-z", "--"))
    paths.extend(git_z_paths(checkout, "diff", "--cached", "--name-only", "-z", "--"))
    paths.extend(
        git_z_paths(checkout, "ls-files", "--others", "--exclude-standard", "-z")
    )
    return normalize_observed_paths(paths)


def observe_branch_paths(
    root: Path | str, *, branch: str, base: str = DEFAULT_BRANCH
) -> tuple[str, ...]:
    """Read committed paths that ``branch`` changes relative to ``base``."""

    merge_base = git_text(root, "merge-base", base, branch)
    return git_z_paths(
        root, "diff", "--name-only", "-z", f"{merge_base}..{branch}", "--"
    )


def observe_repository_state(root: Path | str) -> dict[str, object]:
    """Snapshot the durable Git state of one fixture repository.

    Scenario I2 needs proof that a WAIT changed nothing durable, so the
    snapshot covers HEAD, the tree, every local branch SHA, the tracked file
    list, and the full porcelain status including untracked files.
    """

    return {
        "head": git_text(root, "rev-parse", "HEAD"),
        "tree": git_text(root, "rev-parse", "HEAD^{tree}"),
        "branches": sorted(
            line.strip()
            for line in run_git(
                root, "for-each-ref", "--format=%(refname) %(objectname)", "refs/heads/"
            ).stdout.splitlines()
            if line.strip()
        ),
        "tracked": list(git_z_paths(root, "ls-files", "-z")),
        "status": sorted(
            line
            for line in run_git(
                root, "status", "--porcelain=v1", "--untracked-files=all"
            ).stdout.splitlines()
            if line.strip()
        ),
    }


def make_surface_unobservable(source: SourceFixture, checkout: Path) -> None:
    """Turn a checkout into an unreadable integration surface.

    Scenario G needs a reservation whose surface genuinely cannot be observed.
    Removing the Git metadata is the honest way to produce that: the path still
    exists, so a naive observer would report "no changed paths", which is the
    single most dangerous silent failure the design names.
    """

    root = source.fixture_root.path
    resolved = Path(checkout).resolve()
    if resolved == root or root.resolve() not in resolved.parents:
        raise PathContainmentError(
            f"refusing to modify {resolved}: it is outside the fixture root {root}"
        )
    git_dir = resolved / ".git"
    if not git_dir.is_dir():
        raise AcceptanceFixtureError(f"not a checkout: {resolved}")
    shutil.rmtree(git_dir)


def is_git_checkout(path: Path | str) -> bool:
    root = Path(path)
    if not root.is_dir():
        return False
    result = run_git(root, "rev-parse", "--show-toplevel", check=False)
    if result.returncode != 0:
        return False
    try:
        return Path(result.stdout.strip()).resolve() == root.resolve()
    except OSError:
        return False


def file_roles() -> tuple[dict[str, str], ...]:
    """Machine-readable description of the fixture surface, for the manifest."""

    return tuple(
        {"path": item.path, "kind": item.kind, "role": item.role}
        for item in SYNTHETIC_FILES
    )


def validate_declared_paths(
    paths: Iterable[str], *, where: str = "declared paths"
) -> tuple[str, ...]:
    """Fail closed unless every path is contained and generated by the fixture.

    Containment is checked first, so a traversal attempt such as
    ``SyntheticGame/../../outside.txt`` is rejected as a path before anything
    asks whether the fixture happens to create that file.
    """

    normalized = validate_repository_relative_paths(paths, where=where)
    unknown = [path for path in normalized if path not in SYNTHETIC_FILES_BY_PATH]
    if unknown:
        raise AcceptanceFixtureError(
            f"{where}: the fixture generator never creates " + ", ".join(unknown)
        )
    return normalized


def validate_declared_path(value: str, *, where: str = "declared path") -> str:
    return validate_declared_paths((value,), where=where)[0]


def fixture_relative(source: SourceFixture, relative: str) -> Path:
    """Resolve one repository-relative path inside the source repository."""

    return resolve_within(source.root, validate_repository_relative_path(relative))
