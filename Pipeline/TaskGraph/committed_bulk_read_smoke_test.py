from __future__ import annotations

"""Deterministic proof that committed reads are bulk, exact, and commit-keyed.

``GitRepository`` used to answer every path question with its own Git process,
so ``taskcontrol.py states`` spent one ``cat-file -e`` plus one ``git show``
per task contract and grew a process per task. These scenarios pin the two
properties the bulk read has to keep at once:

* the process count stays bounded and does **not** grow with the number of
  committed tasks; and
* every answer is byte-for-byte the answer the per-object Git command gives,
  including missing paths, directories, empty blobs, binary content, CRLF
  bytes, and names Git has to quote.

The third property is the dangerous one: a bulk view is only sound while it
describes exactly one immutable commit, so a moving name such as ``HEAD`` or a
branch must never be cached and never serve content.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from conformance_records import (  # noqa: E402
    ConformanceRecordError,
    GitRepository,
)
import conformance_records  # noqa: E402

LF_TEXT = b"first\nsecond\nthird\n"
CRLF_BYTES = b"first\r\nsecond\r\n"
BINARY = bytes(range(256)) * 16
SPACED = "Tasks/with space.txt"
NON_ASCII = "Tasks/café-éà.txt"
LARGE = "Tasks/large.bin"
# Deliberately above the size a group read will carry, so the large-blob path
# is exercised. The exactness scenario asserts that relationship still holds.
LARGE_BYTES = 192 * 1024


class DirectRepository(GitRepository):
    """The unchanged per-object implementation, used as the reference answer."""

    def _bulk_reads_supported(self) -> bool:
        return False


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, check=False,
    )
    if result.returncode:
        raise AssertionError(f"git {' '.join(args)} failed:\n{result.stderr}")
    return result.stdout.strip()


def write(root: Path, path: str, payload: bytes) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)


def initialize(root: Path) -> None:
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "bulk-read@example.invalid")
    git(root, "config", "user.name", "Bulk Read Test")
    # Deliberately hostile: end-of-line translation is switched on, so a read
    # that went through a working-tree filter instead of the object store would
    # come back with different bytes.
    git(root, "config", "core.autocrlf", "true")


def commit(root: Path, message: str) -> str:
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message, "--no-gpg-sign")
    return git(root, "rev-parse", "HEAD")


def populate(root: Path, task_count: int) -> str:
    write(root, ".gitattributes", b"*.bin -text\n")
    write(root, "Docs/canon.md", LF_TEXT)
    write(root, "Tasks/empty.txt", b"")
    write(root, SPACED, b"space content\n")
    write(root, NON_ASCII, "unicode éà\n".encode("utf-8"))
    write(root, "Tasks/crlf.bin", CRLF_BYTES)
    write(root, "Tasks/binary.bin", BINARY)
    write(root, LARGE, b"L" * LARGE_BYTES)
    for index in range(task_count):
        task_id = f"NSC-{900 + index:03d}"
        write(root, f"Tasks/{task_id}.yaml", f'{{"id": "{task_id}"}}\n'.encode("utf-8"))
        write(
            root,
            f"Pipeline/TaskGraph/evidence/{task_id}/records/DEL-{task_id}.json",
            f'{{"record_id": "DEL-{task_id}"}}\n'.encode("utf-8"),
        )
        write(
            root,
            f"Pipeline/TaskGraph/evidence/{task_id}/metrics/token-usage.json",
            b'{"total_tokens": 1}\n',
        )
    return commit(root, f"seed {task_count} committed tasks")


def probe_paths(task_count: int) -> list[str]:
    paths = [
        "Docs/canon.md", "Docs", "Tasks", "Tasks/empty.txt", SPACED, NON_ASCII,
        "Tasks/crlf.bin", "Tasks/binary.bin", LARGE, ".gitattributes",
        "Tasks/missing.yaml", "missing", "Pipeline", "Pipeline/TaskGraph",
        "Pipeline/TaskGraph/evidence", "tasks/empty.txt",
    ]
    for index in range(task_count):
        task_id = f"NSC-{900 + index:03d}"
        paths.append(f"Tasks/{task_id}.yaml")
        paths.append(f"Pipeline/TaskGraph/evidence/{task_id}/records/DEL-{task_id}.json")
        paths.append(f"Pipeline/TaskGraph/evidence/{task_id}/metrics/token-usage.json")
        paths.append(f"Pipeline/TaskGraph/evidence/{task_id}/artifacts/absent.log")
    return paths


def outcome(repo: GitRepository, kind: str, commit_id: str, argument: str):
    try:
        if kind == "exists":
            return ("value", repo.exists(commit_id, argument))
        if kind == "blob":
            return ("value", repo.blob(commit_id, argument))
        if kind == "read":
            return ("value", repo.read(commit_id, argument))
        if kind == "files":
            return ("value", repo.files(commit_id, argument))
    except ConformanceRecordError as exc:
        return ("error", str(exc))
    raise AssertionError(kind)


def exercise(repo: GitRepository, commit_id: str, task_count: int) -> None:
    """The access pattern `taskcontrol states` makes, once per committed task."""

    for path in probe_paths(task_count):
        repo.exists(commit_id, path)
    for index in range(task_count):
        task_id = f"NSC-{900 + index:03d}"
        repo.read(commit_id, f"Tasks/{task_id}.yaml")
        prefix = f"Pipeline/TaskGraph/evidence/{task_id}/records"
        for record_path in repo.files(commit_id, prefix):
            repo.read(commit_id, record_path)
            repo.blob(commit_id, record_path)
        repo.read(commit_id, f"Pipeline/TaskGraph/evidence/{task_id}/metrics/token-usage.json")


def count_git_processes(callback) -> int:
    real_run = subprocess.run
    processes = 0

    def counting_run(*args, **kwargs):
        nonlocal processes
        argv = args[0] if args else kwargs.get("args")
        if isinstance(argv, (list, tuple)) and argv and Path(str(argv[0])).name.lower() in {
            "git", "git.exe",
        }:
            processes += 1
        return real_run(*args, **kwargs)

    with mock.patch("conformance_records.subprocess.run", side_effect=counting_run):
        callback()
    return processes


def test_committed_reads_do_not_scale_with_task_count() -> None:
    counts: dict[int, int] = {}
    for task_count in (4, 48):
        with tempfile.TemporaryDirectory(prefix="nsc-bulk-scale-") as temp:
            root = Path(temp)
            initialize(root)
            commit_id = populate(root, task_count)
            repo = GitRepository(root)
            counts[task_count] = count_git_processes(
                lambda: exercise(repo, commit_id, task_count)
            )
    require(
        counts[4] == counts[48],
        f"committed reads still scale with task count: {counts}",
    )
    require(
        counts[48] <= 8,
        f"committed reads used {counts[48]} Git processes for one commit",
    )


def test_bulk_answers_match_the_per_object_commands() -> None:
    task_count = 6
    with tempfile.TemporaryDirectory(prefix="nsc-bulk-exact-") as temp:
        root = Path(temp)
        initialize(root)
        commit_id = populate(root, task_count)
        bulk = GitRepository(root)
        direct = DirectRepository(root)
        require(bulk._bulk_reads_supported(), "bulk reads were unavailable in a normal checkout")
        require(not direct._bulk_reads_supported(), "reference repository was not per-object")

        checked = 0
        for path in probe_paths(task_count):
            for kind in ("exists", "blob", "read"):
                expected = outcome(direct, kind, commit_id, path)
                actual = outcome(bulk, kind, commit_id, path)
                require(
                    expected == actual,
                    f"{kind} {path!r} differs: {str(expected)[:200]} != {str(actual)[:200]}",
                )
                checked += 1
        for prefix in (
            "Tasks", "Docs", "Pipeline", "Pipeline/TaskGraph/evidence/NSC-900/records",
            "Tasks/empty.txt", SPACED, NON_ASCII, "missing", ".gitattributes",
        ):
            expected = outcome(direct, "files", commit_id, prefix)
            actual = outcome(bulk, "files", commit_id, prefix)
            require(expected == actual, f"files {prefix!r} differs: {expected} != {actual}")
            checked += 1
        require(checked >= 100, f"differential coverage collapsed to {checked} comparisons")

        # The committed bytes themselves, not just agreement between two readers.
        require(bulk.read(commit_id, "Docs/canon.md") == LF_TEXT, "LF content was translated")
        require(b"\r" not in bulk.read(commit_id, "Docs/canon.md"), "a CR appeared in LF content")
        require(bulk.read(commit_id, "Tasks/crlf.bin") == CRLF_BYTES, "CRLF bytes were rewritten")
        require(bulk.read(commit_id, "Tasks/binary.bin") == BINARY, "binary content was altered")
        require(bulk.read(commit_id, "Tasks/empty.txt") == b"", "an empty blob was not empty")
        require(
            LARGE_BYTES > conformance_records._BULK_BLOB_MAX_BYTES,
            "the large-blob fixture no longer exceeds the group-read limit",
        )
        require(
            bulk.read(commit_id, LARGE) == b"L" * LARGE_BYTES,
            "a blob above the group-read limit was truncated",
        )


def test_only_resolved_commit_ids_are_cached() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-bulk-moving-") as temp:
        root = Path(temp)
        initialize(root)
        first = populate(root, 2)
        repo = GitRepository(root)

        require(repo.read(first, "Docs/canon.md") == LF_TEXT, "committed read was wrong")
        require(repo.read("HEAD", "Docs/canon.md") == LF_TEXT, "symbolic read was wrong")
        require(repo.exists("main", "Docs/canon.md"), "symbolic exists was wrong")
        require(
            sorted(repo._committed_trees) == [first],
            f"a name that can move was cached: {sorted(repo._committed_trees)}",
        )

        moved = b"canon moved on\n"
        write(root, "Docs/canon.md", moved)
        write(root, "Tasks/NSC-900.yaml", b'{"id": "NSC-900", "revision": 2}\n')
        second = commit(root, "move HEAD")
        require(second != first, "the fixture did not actually move HEAD")

        require(
            repo.read("HEAD", "Docs/canon.md") == moved,
            "a moved HEAD was answered from the previous commit",
        )
        require(
            repo.read("main", "Tasks/NSC-900.yaml") == b'{"id": "NSC-900", "revision": 2}\n',
            "a moved branch was answered from the previous commit",
        )
        require(
            repo.read(first, "Docs/canon.md") == LF_TEXT,
            "the earlier commit stopped reporting its own content",
        )
        require(
            repo.read(second, "Docs/canon.md") == moved,
            "the new commit did not report its own content",
        )
        require(
            all(conformance_records.HEX_RE.fullmatch(key) for key in repo._committed_trees),
            f"a non-commit-id cache key appeared: {sorted(repo._committed_trees)}",
        )


def test_unusable_listings_fall_back_to_git() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-bulk-fallback-") as temp:
        root = Path(temp)
        initialize(root)
        commit_id = populate(root, 2)

        # An unparseable listing must disable the bulk view, not be guessed at.
        with mock.patch(
            "conformance_records._read_committed_tree", return_value=None
        ):
            repo = GitRepository(root)
            require(repo.read(commit_id, "Docs/canon.md") == LF_TEXT, "fallback read was wrong")
            require(repo.exists(commit_id, "Docs/canon.md"), "fallback exists was wrong")
            require(repo.files(commit_id, "Docs") == ["Docs/canon.md"], "fallback files was wrong")

        # A batch that does not answer exactly what was asked must also defer.
        repo = GitRepository(root)
        with mock.patch("conformance_records._read_blob_batch", return_value=None):
            require(
                repo.read(commit_id, "Docs/canon.md") == LF_TEXT,
                "a refused batch did not fall back to git show",
            )

        # An external GIT_DIR means <commit>:<path> and ls-tree can disagree.
        with mock.patch.dict(os.environ, {"GIT_DIR": str(root / ".git")}):
            pointed = GitRepository(root)
            require(not pointed._bulk_reads_supported(), "an external GIT_DIR still used bulk reads")
            require(pointed.read(commit_id, "Docs/canon.md") == LF_TEXT, "pointed read was wrong")


def test_no_cross_commit_leakage_between_reobservations() -> None:
    """One handle used for two observations must answer for each own commit.

    The coherent-snapshot adapter discards an incoherent observation and
    rebuilds the whole thing at whatever state the repository now holds, so a
    second attempt routinely asks the same questions about a *different*
    commit. A bulk view is only sound while it describes exactly one immutable
    commit, so nothing an earlier attempt cached may answer for the later one:
    not a listing, not a blob, not a group memo. Every answer here is compared
    against the unchanged per-object implementation reading the same commit.
    """

    with tempfile.TemporaryDirectory(prefix="nsc-bulk-reobserve-") as temp:
        root = Path(temp)
        initialize(root)
        first = populate(root, 4)

        repo = GitRepository(root)
        require(repo._bulk_reads_supported(), "bulk reads were unavailable")

        # Attempt one: warm every cache the bulk view keeps.
        exercise(repo, first, 4)
        require(repo._committed_trees, "attempt one cached no listing")
        require(repo._committed_blobs, "attempt one cached no blob")
        require(repo._committed_groups, "attempt one recorded no group read")

        # A concurrent apply lands: content changes, a path disappears, a path
        # appears, and a whole evidence directory is replaced.
        moved = b"canon rewritten by the concurrent apply\n"
        write(root, "Docs/canon.md", moved)
        write(root, "Tasks/NSC-900.yaml", b'{"id": "NSC-900", "revision": 2}\n')
        (root / "Tasks" / "NSC-901.yaml").unlink()
        (root / "Pipeline/TaskGraph/evidence/NSC-902/records/DEL-NSC-902.json").unlink()
        write(root, "Tasks/NSC-904.yaml", b'{"id": "NSC-904"}\n')
        write(
            root,
            "Pipeline/TaskGraph/evidence/NSC-902/records/DEL-NSC-902-v2.json",
            b'{"record_id": "DEL-NSC-902-v2"}\n',
        )
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "concurrent apply", "--no-gpg-sign")
        second = git(root, "rev-parse", "HEAD")
        require(second != first, "the fixture did not move the repository")

        # Attempt two, on the SAME handle: every answer must be the second
        # commit's own answer, and the first commit must keep its own.
        reference = DirectRepository(root)
        require(not reference._bulk_reads_supported(), "reference was not per-object")
        compared = 0
        for commit_id in (second, first):
            for path in probe_paths(4) + [
                "Tasks/NSC-904.yaml",
                "Pipeline/TaskGraph/evidence/NSC-902/records/DEL-NSC-902-v2.json",
            ]:
                for kind in ("exists", "blob", "read"):
                    expected = outcome(reference, kind, commit_id, path)
                    actual = outcome(repo, kind, commit_id, path)
                    require(
                        expected == actual,
                        f"{kind} {path!r} at {commit_id[:8]} leaked across attempts: "
                        f"{str(actual)[:200]} != {str(expected)[:200]}",
                    )
                    compared += 1
            for prefix in (
                "Tasks",
                "Docs",
                "Pipeline/TaskGraph/evidence/NSC-902/records",
                "Pipeline/TaskGraph/evidence/NSC-901/records",
            ):
                expected = outcome(reference, "files", commit_id, prefix)
                actual = outcome(repo, "files", commit_id, prefix)
                require(
                    expected == actual,
                    f"files {prefix!r} at {commit_id[:8]} leaked across attempts: "
                    f"{actual} != {expected}",
                )
                compared += 1
        require(compared >= 120, f"leakage coverage collapsed to {compared} comparisons")

        # The two structural invariants that make the above true by construction
        # rather than by luck: a listing is keyed on an exact commit ID, and a
        # blob is keyed on its own content address, so a cached blob is the
        # bytes of that key no matter which commit asked for it.
        require(
            sorted(repo._committed_trees) == sorted({first, second}),
            f"an unexpected listing key appeared: {sorted(repo._committed_trees)}",
        )
        for key, payload in repo._committed_blobs.items():
            require(
                conformance_records.HEX_RE.fullmatch(key) is not None,
                f"a blob cache key was not a content address: {key!r}",
            )
            digest = subprocess.run(
                ["git", "hash-object", "--stdin", "-t", "blob"], cwd=root,
                input=payload, stdout=subprocess.PIPE, check=True,
            ).stdout.decode().strip()
            require(
                digest == key,
                f"cached bytes do not hash to their key {key}: got {digest}",
            )
        for commit_key, _group in repo._committed_groups:
            require(
                commit_key in (first, second),
                f"a group memo was not keyed on an observed commit: {commit_key!r}",
            )

        # A moving name still refuses the cache after both attempts.
        require(
            repo.read("HEAD", "Docs/canon.md") == moved,
            "a moving name was answered from an earlier attempt's listing",
        )
        require(
            sorted(repo._committed_trees) == sorted({first, second}),
            "a moving name entered the listing cache",
        )


def main() -> int:
    tests = (
        test_committed_reads_do_not_scale_with_task_count,
        test_bulk_answers_match_the_per_object_commands,
        test_only_resolved_commit_ids_are_cached,
        test_no_cross_commit_leakage_between_reobservations,
        test_unusable_listings_fall_back_to_git,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print("committed_bulk_read_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
