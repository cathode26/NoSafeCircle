#!/usr/bin/env python3
"""Pre-merge propagation check for the No Safe Circle repository.

Given a clone and a commit range, answer two questions a reviewer cannot
answer by eye before merging:

  1. Which module-level names disappeared between base and head, and where
     are they still referenced (Python, PowerShell, Markdown, YAML and
     especially .github/workflows)?
  2. Which test files import the modules that changed, and which of those
     tests does CI actually run?

Question 2 is the one that earns its keep. The release that motivated this
tool broke three times on changes that removed no symbol at all -- a string
was dropped from the *value* of a tuple, and tests asserting counts derived
from that tuple failed. No grep for a name finds that. Running the tests
that import the changed module does.

Standard library only. Never imports the repository under test; the base
and head revisions are parsed with `ast` from `git show` output.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

# A console window flashing on the operator's machine interrupts him.
# DETACHED_PROCESS is forbidden; CREATE_NO_WINDOW is the allowed form.
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
# Its own process group, so a Ctrl-C to this tool does not race the test.
# It plays NO part in the timeout kill - that is taskkill /T - and an earlier
# comment here claimed it did. Never DETACHED_PROCESS.
CREATE_NEW_PROCESS_GROUP = 0x00000200 if sys.platform == "win32" else 0

WORKFLOW_DIR = ".github/workflows"

TEST_PATH_PATTERN = re.compile(
    r"(^|/)tests?/|(^|/)test_[^/]*\.py$|(^|/)[^/]*_test\.py$"
)

PY_PATH_IN_TEXT = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./\\-]*\.py")

LIMITS_TEXT = [
    "A change to the VALUE of a constant removes no name, so steps 2 and 3",
    "report nothing for it. That is the exact shape that broke PR #134.",
    "Step 4 is what covers it: it selects every test that imports the changed",
    "module, whether or not any symbol was removed. Trust step 4, not step 2.",
    "Step 3 is a literal text grep: it cannot tell a removed symbol from an",
    "unrelated word that happens to match, and it does not resolve aliases.",
    "Step 4 matches import statements textually. A module reached only by",
    "importlib, a plugin registry, a subprocess or a data file is not found.",
    "Only module-level names are compared; methods and nested names are not.",
]


class CheckError(RuntimeError):
    """A failure the caller should see as a message, not a traceback."""


# --------------------------------------------------------------------------
# git plumbing
# --------------------------------------------------------------------------


def git(clone: str, args: Sequence[str], allowed: Sequence[int] = (0,)) -> Tuple[int, str]:
    """Run git in the clone, returning (exit code, stdout).

    stderr is kept out of stdout so a warning can never become a filename.
    """
    proc = subprocess.run(
        ["git", "-C", clone] + list(args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=CREATE_NO_WINDOW,
    )
    if proc.returncode not in allowed:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise CheckError(
            "git %s failed with exit code %d: %s"
            % (" ".join(args[:3]), proc.returncode, detail)
        )
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


def cat_file_batch(clone: str, specs: Sequence[str]) -> Dict[str, Optional[str]]:
    """Read many `<rev>:<path>` blobs in a single git process.

    One `git show` per file costs a process spawn each; on a large repository
    that is the whole runtime. Missing blobs map to None rather than failing.
    """
    result: Dict[str, Optional[str]] = {spec: None for spec in specs}
    if not specs:
        return result
    proc = subprocess.run(
        ["git", "-C", clone, "cat-file", "--batch"],
        input=("\n".join(specs) + "\n").encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=CREATE_NO_WINDOW,
    )
    if proc.returncode != 0:
        raise CheckError(
            "git cat-file --batch failed: %s"
            % proc.stderr.decode("utf-8", "replace").strip()
        )
    data = proc.stdout
    offset = 0
    for spec in specs:
        end = data.find(b"\n", offset)
        if end == -1:
            break
        header = data[offset:end].decode("utf-8", "replace")
        offset = end + 1
        parts = header.rsplit(" ", 2)
        if len(parts) != 3 or not parts[2].isdigit():
            continue  # "<spec> missing"
        size = int(parts[2])
        result[spec] = data[offset:offset + size].decode("utf-8", "replace")
        offset += size + 1  # trailing newline git appends after the object
    return result


def parse_range(rev_range: str) -> Tuple[str, str]:
    if "..." in rev_range:
        base, _, head = rev_range.partition("...")
    elif ".." in rev_range:
        base, _, head = rev_range.partition("..")
    else:
        raise CheckError("range must look like <base>..<head>, got %r" % rev_range)
    base, head = base.strip(), head.strip()
    if not base or not head:
        raise CheckError("range must name both a base and a head: %r" % rev_range)
    return base, head


# --------------------------------------------------------------------------
# step 1: changed modules
# --------------------------------------------------------------------------


def module_path_for(path: str) -> Optional[str]:
    """Map Pipeline/ExecutionCrew/session_pool.py -> Pipeline.ExecutionCrew.session_pool."""
    if not path.endswith(".py"):
        return None
    parts = path[: -len(".py")].split("/")
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts:
        return None
    if not all(p.isidentifier() for p in parts):
        return None
    return ".".join(parts)


@dataclass
class ChangedFile:
    path: str
    module: Optional[str]


def changed_files(clone: str, base: str, head: str) -> Tuple[List[ChangedFile], List[str]]:
    # --no-renames, and it is not cosmetic. Git scores a rename-plus-small-edit
    # as R090 and then reports ONLY the new path, so every name in the old
    # module looked untouched: step 2 printed "no module-level name present at
    # base is absent at head" - which is false, they are all gone - step 4
    # selected nothing, and --run said "0 run, 0 failed", exit 0, while the
    # test CI actually runs died with ModuleNotFoundError. A plain `git rm`
    # always worked; only the rename path produced that confident green.
    _, out = git(clone, ["diff", "--no-renames", "--name-only", "%s..%s" % (base, head)])
    python: List[ChangedFile] = []
    other: List[str] = []
    for line in out.splitlines():
        path = line.strip()
        if not path:
            continue
        if path.endswith(".py"):
            python.append(ChangedFile(path=path, module=module_path_for(path)))
        else:
            other.append(path)
    return python, other


# --------------------------------------------------------------------------
# step 2: removed or renamed module-level symbols
# --------------------------------------------------------------------------


def module_level_names(source: str) -> Set[str]:
    """Module-level functions, classes, assignment targets and __all__ entries."""
    tree = ast.parse(source)
    names: Set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                names.update(_target_names(target))
            names.update(_dunder_all_entries(node.targets, node.value))
        elif isinstance(node, ast.AnnAssign):
            names.update(_target_names(node.target))
            if node.value is not None:
                names.update(_dunder_all_entries([node.target], node.value))
        elif isinstance(node, ast.AugAssign):
            names.update(_target_names(node.target))
    return names


def _target_names(target: ast.AST) -> Set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        found: Set[str] = set()
        for element in target.elts:
            found |= _target_names(element)
        return found
    if isinstance(target, ast.Starred):
        return _target_names(target.value)
    return set()


def _dunder_all_entries(targets: Iterable[ast.AST], value: ast.AST) -> Set[str]:
    is_all = any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets)
    if not is_all or not isinstance(value, (ast.Tuple, ast.List, ast.Set)):
        return set()
    return {
        element.value
        for element in value.elts
        if isinstance(element, ast.Constant) and isinstance(element.value, str)
    }


@dataclass
class RemovedSymbol:
    name: str
    file: str
    hits: List[Dict[str, object]] = field(default_factory=list)
    hit_total: int = 0
    external_total: int = 0


def removed_symbols(
    clone: str, base: str, head: str, files: Sequence[ChangedFile]
) -> Tuple[List[RemovedSymbol], List[str]]:
    removed: List[RemovedSymbol] = []
    unparsed: List[str] = []
    specs: List[str] = []
    for changed in files:
        specs.append("%s:%s" % (base, changed.path))
        specs.append("%s:%s" % (head, changed.path))
    blobs = cat_file_batch(clone, specs)
    for changed in files:
        base_src = blobs.get("%s:%s" % (base, changed.path))
        head_src = blobs.get("%s:%s" % (head, changed.path))
        if base_src is None:
            continue  # added at head: nothing can have been removed
        try:
            base_names = module_level_names(base_src)
            head_names = module_level_names(head_src) if head_src is not None else set()
        except SyntaxError as exc:
            unparsed.append("%s (%s)" % (changed.path, exc.msg))
            continue
        for name in sorted(base_names - head_names):
            removed.append(RemovedSymbol(name=name, file=changed.path))
    return removed, unparsed


# --------------------------------------------------------------------------
# step 3: stale references
# --------------------------------------------------------------------------


GREP_BATCH = 100

# Per-test wall clock for --run. There was none, so one hung test blocked the
# whole run indefinitely. A real --run over this repo took 366s for 22 tests,
# so the cap is per test and generous rather than tight.
RUN_TIMEOUT_SECONDS = 900.0


def _strip_rev_prefix(line: str, rev: str) -> str:
    """`git grep <rev>` prefixes every hit with `<rev>:`. Remove it.

    Without this the path comes back as the revision itself and every hit is
    attributed to a file named after the sha.
    """
    prefix = rev + ":"
    return line[len(prefix):] if line.startswith(prefix) else line


def grep_symbols(
    clone: str, names: Sequence[str], rev: str
) -> Dict[str, List[Tuple[str, int, str]]]:
    """Fixed-string git grep for every removed name, batched into few processes.

    `git grep -F` accepts many `-e` patterns in one pass over the tree, so the
    cost is a pass over tracked files rather than one pass per symbol. Each
    returned line is then attributed to whichever names it literally contains.

    Searches `rev`, NOT the working tree. Two independent reviews on 2026-09-18
    found the same blocking defect here: this searched whatever the clone
    happened to have checked out, so asking about a feature branch from a clone
    sitting on `main` reported "no references, nothing selected, exit 0" - a
    confident false green in exactly the posture the runbook would use it in.
    """
    found: Dict[str, List[Tuple[str, int, str]]] = {name: [] for name in names}
    unique = sorted(set(names))
    for start in range(0, len(unique), GREP_BATCH):
        batch = unique[start:start + GREP_BATCH]
        args = ["grep", "-n", "-I", "-F"]
        for name in batch:
            args += ["-e", name]
        args += [rev, "--", "."]
        code, out = git(clone, args, allowed=(0, 1))
        if code == 1:
            continue
        for line in out.splitlines():
            path, sep, rest = _strip_rev_prefix(line, rev).partition(":")
            if not sep:
                continue
            lineno, sep2, text = rest.partition(":")
            if not sep2 or not lineno.isdigit():
                continue
            stripped = text.strip()
            for name in batch:
                if name in stripped:
                    found[name].append((path, int(lineno), stripped))
    return found


def attach_references(
    clone: str, symbols: Sequence[RemovedSymbol], changed_paths: Set[str], limit: int,
    rev: str,
) -> None:
    seen = grep_symbols(clone, [s.name for s in symbols], rev)
    for symbol in symbols:
        hits = seen[symbol.name]
        symbol.hit_total = len(hits)
        external = [h for h in hits if h[0] not in changed_paths]
        symbol.external_total = len(external)
        ordered = external + [h for h in hits if h[0] in changed_paths]
        for path, lineno, text in ordered[: max(limit, 0)] if limit >= 0 else ordered:
            symbol.hits.append(
                {
                    "file": path,
                    "line": lineno,
                    "text": text,
                    "in_changed_file": path in changed_paths,
                    "in_workflow": path.startswith(WORKFLOW_DIR),
                }
            )


# --------------------------------------------------------------------------
# step 4: tests importing the changed modules
# --------------------------------------------------------------------------


# One cheap grep finds every import statement; Python decides what they name.
# Handing git one alternation per changed module does not scale: a range with
# a few hundred changed modules turns into a minutes-long regex pass.
ANY_IMPORT_ERE = r"^[[:space:]]*(from|import)[[:space:]]"

IMPORT_LINE = re.compile(
    r"^\s*(?:from\s+(?P<pkg>[.\w]+)\s+import\s+(?P<names>.*)"
    r"|import\s+(?P<mods>[\w.,\s]+))$"
)


def modules_named_by_import_line(line: str, owner_module: Optional[str]) -> Set[str]:
    """Dotted modules an import statement refers to.

    `from a.b import c` names `a.b` and, if `c` is a submodule, `a.b.c`; both
    are returned and the caller keeps whichever it actually changed. Relative
    imports are resolved against the importing file's own package.
    """
    match = IMPORT_LINE.match(line)
    if match is None:
        return set()

    found: Set[str] = set()
    pkg = match.group("pkg")
    if pkg is not None:
        base = _resolve_relative(pkg, owner_module)
        if base is None:
            return set()
        if base:
            found.add(base)
        raw = match.group("names").split("#", 1)[0]
        raw = raw.replace("(", " ").replace(")", " ")
        for item in raw.split(","):
            name = item.strip().split(" as ")[0].strip()
            if name and name != "*" and name.isidentifier():
                found.add("%s.%s" % (base, name) if base else name)
        return found

    for item in (match.group("mods") or "").split(","):
        name = item.strip().split(" as ")[0].strip()
        if name and all(p.isidentifier() for p in name.split(".")):
            found.add(name)
    return found


def _resolve_relative(pkg: str, owner_module: Optional[str]) -> Optional[str]:
    if not pkg.startswith("."):
        return pkg
    depth = len(pkg) - len(pkg.lstrip("."))
    tail = pkg[depth:]
    if owner_module is None:
        return None
    parts = owner_module.split(".")[:-1]  # the importing file's package
    if depth - 1 > len(parts):
        return None
    if depth > 1:
        parts = parts[: len(parts) - (depth - 1)]
    if tail:
        parts = parts + tail.split(".")
    return ".".join(parts)


def is_test_path(path: str) -> bool:
    return path.endswith(".py") and bool(TEST_PATH_PATTERN.search(path))


DOTTED_TEST_ID = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*\.[A-Za-z_][A-Za-z0-9_]*")


def _plain_test_case_bases(node: ast.ClassDef) -> bool:
    """True only when every base is literally TestCase / unittest.TestCase.

    A mixin, another test class, or anything computed means members can arrive
    from somewhere this file does not show, so the class cannot be used to
    prove an id absent.
    """
    if not node.bases or node.keywords:
        return False
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id == "TestCase":
            continue
        if (isinstance(base, ast.Attribute) and base.attr == "TestCase"
                and isinstance(base.value, ast.Name) and base.value.id == "unittest"):
            continue
        return False
    return True


def class_bindings(source: str) -> Dict[str, Optional[Set[str]]]:
    """Every name bound in each class body, or None when it cannot be trusted.

    None means "do not conclude anything from this class". A review found six
    LIVE test ids reported stale because the first version counted only
    `FunctionDef` nodes in `tree.body`: methods inherited from a mixin,
    `test_alias = test_direct`, a method assigned from a factory, a `def`
    inside an `if` in the class body, and a class nested under a module-level
    `if`. A false stale id exits 1, so it is as harmful as a miss.

    A later review found three more shapes, all adding methods from OUTSIDE
    the class body so the scan above cannot see them: a `setattr(Cls, ...)`
    parametrise loop after the class, `Cls.name = fn` after the class body,
    and a class decorator (`decorator_list` was never inspected). All three
    widen None rather than trying to be clever about what they add.
    """
    bindings: Dict[str, Optional[Set[str]]] = {}
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return bindings
    # ast.walk, not tree.body: a class guarded by `if sys.platform == ...`
    # is still a class.
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        # A decorator can add or replace anything the body does not show.
        if node.decorator_list or not _plain_test_case_bases(node):
            names: Optional[Set[str]] = None
        else:
            names = set()
            for child in ast.walk(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    names.add(child.name)
                elif isinstance(child, ast.Assign):
                    for target in child.targets:
                        names.update(_target_names(target))
                elif isinstance(child, ast.AnnAssign):
                    names.update(_target_names(child.target))
        # A duplicate class name means two definitions; trust neither.
        bindings[node.name] = None if node.name in bindings else names

    # A second pass for methods added from OUTSIDE the class body. `setattr`
    # on a known class means unverifiable outright - the attribute name may
    # not even be a literal, and any setattr on the class is enough to doubt
    # it. `Cls.name = fn` is precise enough to add just that one name, which
    # keeps the class able to catch an unrelated rename. A class already None
    # for any reason stays None.
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "setattr" and node.args:
                target = node.args[0]
                if isinstance(target, ast.Name) and target.id in bindings:
                    bindings[target.id] = None
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if not (isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Name)):
                    continue
                class_name = target.value.id
                if class_name not in bindings or bindings[class_name] is None:
                    continue
                bindings[class_name].add(target.attr)
    return bindings


def strip_yaml_comments(text: str) -> str:
    """Drop `#` comments so a retired, commented-out CI line is not reported.

    Crude on purpose - a `#` inside a quoted string is rare in these workflows
    and losing the rest of such a line only costs a possible finding, never a
    false one.
    """
    out = []
    for line in (text or "").splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        marker = line.find(" #")
        out.append(line[:marker] if marker != -1 else line)
    return "\n".join(out)


def stale_workflow_test_ids(
    clone: str, rev: str, workflow_text: str, tests: Sequence["SelectedTest"]
) -> List[Dict[str, str]]:
    """Dotted `module.Class.method` ids a workflow names that head does not have.

    CI runs named method ids, and the symbol diff is module-level, so renaming
    a method left `--run` reporting "1 run, 0 failed" on a file whose CI
    command dies with errors=1. Green while red - which is the class of defect
    this tool exists to prevent, so it is worth the extra AST pass even though
    it only covers ids a workflow spells out.
    """
    by_module = {}
    for test in tests:
        # An __init__.py maps to the PACKAGE name, so `pkg.tests` would claim
        # the id `pkg.tests.test_viewer.ViewerTests` and read `test_viewer`
        # as a class inside __init__.py. It never owns a Class.method id.
        if test.path.endswith("__init__.py"):
            continue
        dotted = module_path_for(test.path)
        if dotted:
            by_module[dotted] = test.path
    if not by_module:
        return []
    sources = cat_file_batch(clone, ["%s:%s" % (rev, p) for p in by_module.values()])
    bindings = {
        module: class_bindings(sources.get("%s:%s" % (rev, path)) or "")
        for module, path in by_module.items()
    }
    stale: List[Dict[str, str]] = []
    seen: Set[str] = set()
    for candidate in DOTTED_TEST_ID.findall(strip_yaml_comments(workflow_text)):
        for module, path in by_module.items():
            if not candidate.startswith(module + "."):
                continue
            suffix = candidate[len(module) + 1:]
            if suffix.count(".") != 1:
                continue  # Class alone, or something deeper than Class.method
            class_name, _, member = suffix.partition(".")
            known = bindings[module].get(class_name, "missing")
            # Report ONLY what can be proved absent: the class is here, its
            # bases are plainly TestCase, and the name is bound nowhere in it.
            # Anything else - class not found, a mixin, a computed base - is
            # unverifiable, and an unverifiable id must not fail the check.
            if known in (None, "missing") or member in known or candidate in seen:
                continue
            seen.add(candidate)
            stale.append({"id": candidate, "file": path})
    return sorted(stale, key=lambda entry: entry["id"])


def tracked_paths(clone: str, rev: str) -> List[str]:
    _, listing = git(clone, ["ls-tree", "-r", "--name-only", rev], allowed=(0, 1))
    return [p.strip() for p in listing.splitlines() if p.strip()]


def head_matches_worktree(clone: str, head: str) -> Tuple[bool, str, str]:
    """Is the clone actually checked out at `head`?

    Only `--run` needs this: the analysis reads git directly, but the tests
    execute against whatever is on disk. Running them from a tree that is not
    `head` measures a revision nobody asked about - and a reviewer proved it
    silently does, with all four real regressions replaced by unrelated ones.
    """
    _, resolved_head = git(clone, ["rev-parse", "%s^{commit}" % head])
    _, resolved_worktree = git(clone, ["rev-parse", "HEAD^{commit}"], allowed=(0, 128))
    a, b = resolved_head.strip(), resolved_worktree.strip()
    return (bool(a) and a == b), a, b


def worktree_is_dirty(clone: str) -> bool:
    """Uncommitted changes to tracked files.

    The commit comparison alone is not enough: a clone detached at the head
    with an edited file passes it and then runs something that is not the head.
    A reviewer reproduced exactly that - both tests green, exit 0,
    `run_tree_was_head: true`, while the real head was red.
    """
    return bool(worktree_status(clone).strip())


def worktree_status(clone: str, untracked: bool = False) -> str:
    """`git status --porcelain`, without touching the clone.

    `--no-optional-locks`: plain `git status` refreshes `.git/index`, so this
    tool - which calls itself read-only and may be pointed at a live checkout
    under C:\\NSC - was rewriting the index and opening an `index.lock` window
    for whatever else was using that repository.
    """
    # `=all`, not `=normal`: normal collapses a whole new directory to
    # `?? pkg/helpers/`, which does not end in .py - so a new untracked
    # PACKAGE, the commonest shape of a forgotten `git add`, was invisible.
    mode = "--untracked-files=all" if untracked else "--untracked-files=no"
    _, status = git(
        clone, ["--no-optional-locks", "status", "--porcelain", mode], allowed=(0, 128)
    )
    return status


def untracked_python_files(clone: str) -> List[str]:
    """Untracked, non-ignored .py files sitting in the tree.

    `--untracked-files=no` is blind to a forgotten `git add`: the head commits
    a module that imports a helper, the helper exists only on disk, --run
    passes, and a fresh clone of the same head dies with ModuleNotFoundError.
    Not a refusal - an untracked file is usually noise - but the report must
    say so rather than call the tree clean.
    """
    found: List[str] = []
    for line in worktree_status(clone, untracked=True).splitlines():
        if line.startswith("?? ") and line[3:].strip().endswith(".py"):
            found.append(line[3:].strip().strip('"'))
    return sorted(found)


def workflow_references(clone: str, rev: str) -> Tuple[Set[str], str]:
    """Every .py path mentioned under .github/workflows, plus the raw text.

    The raw text matters because this repository also names test targets in
    dotted `python -m unittest Pipeline.X.tests.y_test` form, which is not a
    path and would otherwise be missed.
    """
    _, listing = git(
        clone, ["ls-tree", "-r", "--name-only", rev, "--", WORKFLOW_DIR], allowed=(0, 1)
    )
    workflows = [w.strip() for w in listing.splitlines() if w.strip()]
    referenced: Set[str] = set()
    chunks: List[str] = []
    # `HEAD:` read the checked-out branch's workflows, not the revision under
    # test - so a branch that added or changed a CI target was judged against
    # whatever CI looked like on the clone's current branch.
    blobs = cat_file_batch(clone, ["%s:%s" % (rev, wf) for wf in workflows])
    for text in blobs.values():
        if text is None:
            continue
        chunks.append(text)
        for match in PY_PATH_IN_TEXT.finditer(text):
            referenced.add(match.group(0).replace("\\", "/").lstrip("./"))
    return referenced, "\n".join(chunks)


@dataclass
class SelectedTest:
    path: str
    modules: List[str] = field(default_factory=list)
    in_ci: bool = False


def importing_tests(
    clone: str, modules: Sequence[str], rev: str
) -> Tuple[List[SelectedTest], int]:
    """One combined git grep over tracked .py files, then attribute per module.

    Searches `rev`, not the working tree: see `grep_symbols`.
    """
    if not modules:
        return [], 0
    wanted = set(modules)
    # Restrict to test-shaped paths so the grep touches a fraction of the tree.
    args = ["grep", "-n", "-I", "-E", "-e", ANY_IMPORT_ERE,
            rev, "--", "*_test.py", "*test_*.py", "*/tests/*.py", "tests/*.py"]
    code, out = git(clone, args, allowed=(0, 1))
    if code == 1:
        return [], 0
    found: Dict[str, SelectedTest] = {}
    owners: Dict[str, Optional[str]] = {}
    lines_scanned = 0
    for line in out.splitlines():
        path, sep, rest = _strip_rev_prefix(line, rev).partition(":")
        if not sep or not is_test_path(path):
            continue
        _, sep2, text = rest.partition(":")
        if not sep2:
            continue
        lines_scanned += 1
        if path not in owners:
            owners[path] = module_path_for(path)
        hit = modules_named_by_import_line(text, owners[path]) & wanted
        if not hit:
            continue
        entry = found.setdefault(path, SelectedTest(path=path))
        for module in hit:
            if module not in entry.modules:
                entry.modules.append(module)
    for entry in found.values():
        entry.modules.sort()
    return [found[p] for p in sorted(found)], lines_scanned


# --------------------------------------------------------------------------
# --run
# --------------------------------------------------------------------------


def kill_process_tree(proc: "subprocess.Popen") -> None:
    """Kill the test AND anything it started.

    `proc.kill()` alone leaves grandchildren running - a reviewer found an
    orphaned `python -c "time.sleep(25)"` still alive after a timeout. On
    Windows `taskkill /T` walks the tree; the fallbacks keep this honest
    elsewhere and if taskkill is missing.
    """
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
                creationflags=CREATE_NO_WINDOW,
            )
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        proc.kill()
    except OSError:
        pass
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        pass


def last_meaningful_line(text: str) -> str:
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if stripped:
            return stripped[:200]
    return "(no output)"


def run_at_baseline(
    clone: str, base: str, tests: Sequence[SelectedTest], timeout: Optional[float] = None
) -> Dict[str, object]:
    """Run the same tests at `base`, in a throwaway worktree.

    Without this a red test is not evidence: every reviewer round said so, and
    a real run of this tool had 10 failures of which 2 were pre-existing. The
    tool could state the caveat but not resolve it.

    This is the ONE operation that writes to the clone - `git worktree add`
    records administrative state under `.git/worktrees` - so it is opt-in
    behind `--baseline` and removed in a `finally`. A stale entry from a kill
    is pruned on the next run rather than left to rot.
    """
    git(clone, ["worktree", "prune"], allowed=(0, 1, 128))
    holder = tempfile.mkdtemp(prefix="propcheck-base-")
    tree = os.path.join(holder, "base")
    try:
        git(clone, ["worktree", "add", "--detach", "--quiet", tree, base])
    except CheckError as exc:
        shutil.rmtree(holder, ignore_errors=True)
        return {"error": str(exc), "results": []}
    try:
        present = [t for t in tests if os.path.isfile(os.path.join(tree, t.path))]
        absent = [t.path for t in tests if t not in present]
        results = run_tests(tree, present, timeout)
        return {
            "error": None,
            "results": results,
            "not_present_at_base": sorted(absent),
        }
    finally:
        git(clone, ["worktree", "remove", "--force", tree], allowed=(0, 1, 128))
        shutil.rmtree(holder, ignore_errors=True)
        git(clone, ["worktree", "prune"], allowed=(0, 1, 128))


def classify_against_baseline(
    head_results: Sequence[Dict[str, object]], baseline: Dict[str, object]
) -> None:
    """Label each head result regression / pre-existing / fixed / new.

    Mutates `head_results` in place, adding `verdict`. Without a baseline the
    verdict is `unknown`, which is honest rather than absent.
    """
    if baseline is None or baseline.get("error"):
        for result in head_results:
            result["verdict"] = "unknown"
        return
    at_base = {r["test"]: r.get("status") for r in baseline.get("results", [])}
    for result in head_results:
        before = at_base.get(result["test"])
        now = result.get("status")
        if before is None:
            result["verdict"] = "new-at-head" if now != "pass" else "pass"
        elif now != "pass" and before != "pass":
            result["verdict"] = "pre-existing"
        elif now != "pass":
            result["verdict"] = "REGRESSION"
        elif before != "pass":
            result["verdict"] = "fixed"
        else:
            result["verdict"] = "pass"


def run_tests(
    clone: str, tests: Sequence[SelectedTest], timeout: Optional[float] = None
) -> List[Dict[str, object]]:
    # Read at call time, not bound as a default: `timeout=RUN_TIMEOUT_SECONDS`
    # in the signature freezes the value at import, so neither a caller nor a
    # test could change it and the constant only looked configurable.
    if timeout is None:
        timeout = RUN_TIMEOUT_SECONDS
    results: List[Dict[str, object]] = []
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = clone + (os.pathsep + existing if existing else "")
    scratch = tempfile.mkdtemp(prefix="propcheck-")
    env["TMPDIR"] = scratch
    env["TEMP"] = scratch
    env["TMP"] = scratch
    env.setdefault("PYTHONPYCACHEPREFIX", os.path.join(scratch, "pyc"))
    try:
        for test in tests:
            started = time.time()
            # Output goes to a FILE, not a pipe. With a pipe, `subprocess.run`
            # kills only the direct child on timeout and then blocks reading a
            # pipe a surviving grandchild still holds - so a test that starts a
            # server was reported as "timeout" only when its grandchild
            # happened to exit, which is the hang the timeout exists to stop.
            log = os.path.join(scratch, "out-%d.log" % len(results))
            timed_out = False
            with open(log, "wb") as sink:
                proc = subprocess.Popen(
                    [sys.executable, "-B", test.path],
                    cwd=clone,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=sink,
                    stderr=subprocess.STDOUT,
                    creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP,
                )
                try:
                    returncode = proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    returncode = None
                    kill_process_tree(proc)
            with open(log, "rb") as handle:
                output = handle.read().decode("utf-8", "replace")
            seconds = round(time.time() - started, 2)
            # The verdict comes from the exit code alone. `last_line` is
            # context and nothing more: a suite that prints a per-case
            # "PASS ..." as its final line while exiting 1 read as passing.
            status = "timeout" if timed_out else ("pass" if returncode == 0 else "fail")
            results.append(
                {
                    "test": test.path,
                    "exit_code": returncode,
                    "status": status,
                    "seconds": seconds,
                    "last_line": last_meaningful_line(output),
                }
            )
            sys.stderr.write(
                "  %-7s %6.1fs  %s\n" % (status, seconds, test.path)
            )
            sys.stderr.flush()
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return results


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------


def build_report(data: Dict[str, object], limit: int) -> str:
    out: List[str] = []
    add = out.append
    add("propagation check  %s..%s" % (data["base"], data["head"]))
    add("clone: %s" % data["clone"])
    add("")

    py_files = data["changed_python_files"]
    add("1. CHANGED PYTHON FILES (%d)" % len(py_files))
    if not py_files:
        add("   none")
    for entry in py_files:
        module = entry["module"] or "(not importable as a module)"
        add("   %s  ->  %s" % (entry["path"], module))
    other = data["changed_other_files"]
    if other:
        add("   plus %d non-Python file(s) changed, not analysed here" % len(other))
    add("")

    symbols = data["removed_symbols"]
    add("2+3. REMOVED OR RENAMED MODULE-LEVEL SYMBOLS, WITH STALE REFERENCES (%d)"
        % len(symbols))
    if not symbols:
        add("   none - no module-level name present at base is absent at head.")
        add("   This does NOT mean nothing broke; see LIMITS below, then step 4.")
    for symbol in symbols:
        add("   %s  (removed from %s)" % (symbol["name"], symbol["file"]))
        if symbol["external_reference_count"] == 0:
            add("      no references outside the changed files")
        for hit in symbol["hits"]:
            tag = ""
            if hit["in_changed_file"]:
                tag = "  [same changed file - likely the rename itself]"
            elif hit["in_workflow"]:
                tag = "  [CI WORKFLOW]"
            add("      %s:%d: %s%s" % (hit["file"], hit["line"], hit["text"], tag))
        shown = len(symbol["hits"])
        if symbol["reference_count"] > shown:
            add("      ... %d more hit(s) not shown (--limit %d)"
                % (symbol["reference_count"] - shown, limit))
    add("")

    tests = data["importing_tests"]
    ci_count = sum(1 for t in tests if t["in_ci"])
    add("4. TESTS THAT IMPORT THE CHANGED MODULES (%d, of which %d referenced by %s)"
        % (len(tests), ci_count, WORKFLOW_DIR))
    if not tests:
        add("   none - no tracked test file imports any changed module.")
    for test in tests:
        marker = "[CI]" if test["in_ci"] else "[   ]"
        add("   %s %s" % (marker, test["path"]))
        add("         imports: %s" % ", ".join(test["modules"]))
    add("")

    add("5. RUN THESE (from %s, PYTHONPATH=%s)" % (data["clone"], data["clone"]))
    if not tests:
        add("   nothing selected")
    for test in tests:
        add("   python -B %s" % test["path"])
    if not data.get("worktree_at_head", True):
        # Without this the report offers commands for files that are not on
        # disk, from a clone it never says is on the wrong commit.
        add("")
        add("   !! this clone is checked out at %s, not at the head (%s), so some of"
            % ((data.get("worktree_commit") or "an unknown commit")[:12], data["head"]))
        add("      these files may not exist here. The analysis above is correct - it")
        add("      reads git - but run them from a checkout of the head:")
        add("          git -C %s checkout --detach %s" % (data["clone"], data["head"]))
    add("")

    stale_ids = data.get("stale_workflow_test_ids") or []
    if stale_ids:
        add("!! STALE WORKFLOW TEST IDS (%d)" % len(stale_ids))
        add("   These ids no longer exist at head, but CI runs them by name.")
        for entry in stale_ids:
            add("   %s   (%s)" % (entry["id"], entry["file"]))
        add("")

    untracked = data.get("untracked_python_files") or []
    if untracked:
        add("!! UNTRACKED .py FILES IN THIS CHECKOUT (%d)" % len(untracked))
        add("   A forgotten `git add` makes --run pass here and fail in a fresh clone.")
        for path in untracked[:10]:
            add("   %s" % path)
        if len(untracked) > 10:
            add("   ... and %d more" % (len(untracked) - 10))
        add("")

    runs = data.get("run_results")
    if runs is not None:
        failed = sum(1 for r in runs if r.get("status") != "pass")
        add("6. --run RESULTS (%d run, %d failed)" % (len(runs), failed))
        for result in runs:
            # `exit_code` is None on a timeout, and "%d" % None is a TypeError
            # that threw away the whole report after the run had already spent
            # up to the timeout on every test.
            code = result.get("exit_code")
            shown = "exit %-3d" % code if isinstance(code, int) else "%-8s" % "TIMEOUT"
            verdict = result.get("verdict", "unknown")
            mark = {
                "REGRESSION": "  <-- REGRESSION",
                "pre-existing": "  (already red at base)",
                "fixed": "  (was red at base)",
                "new-at-head": "  (not present at base)",
                "unknown": "  (no baseline)" if result.get("status") != "pass" else "",
            }.get(verdict, "")
            add("   %s %6.2fs  %s%s" % (shown, result["seconds"], result["test"], mark))
            add("                    %s" % result["last_line"])
        add("")
        if not data.get("run_tree_was_head", True):
            add("   !! THESE RESULTS ARE NOT THIS RANGE'S. The clone was checked out at")
            add("      %s, not at the head, and --run-on-current-tree was given."
                % (data.get("worktree_commit") or "an unknown commit"))
            add("")
        if data.get("run_dirty_worktree"):
            add("   !! The working tree had uncommitted changes to tracked files, so what")
            add("      ran is not exactly the head either.")
            add("")
        if data.get("run_caveat"):
            add("   !! NO BASELINE: %s" % data["run_caveat"])
            add("")
        baseline = data.get("run_baseline")
        if baseline and not baseline.get("error"):
            regressions = [r for r in runs if r.get("verdict") == "REGRESSION"]
            add("   baseline at %s: %d regression(s), %d pre-existing failure(s)"
                % (data["base"], len(regressions),
                   sum(1 for r in runs if r.get("verdict") == "pre-existing")))
            for path in baseline.get("not_present_at_base") or []:
                add("   (not present at base, so not compared) %s" % path)
            add("")

    if data.get("unparsed_files"):
        add("NOTE: could not parse with ast (skipped in step 2):")
        for entry in data["unparsed_files"]:
            add("   %s" % entry)
        add("")

    add("LIMITS - read these before trusting a clean report")
    for line in LIMITS_TEXT:
        add("   %s" % line)
    add("")
    add("timings: steps 1-4 %.2fs%s"
        % (data["seconds_analysis"],
           "" if runs is None else ", --run %.2fs" % data["seconds_run"]))
    return "\n".join(out)


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------


def analyse(clone: str, rev_range: str, limit: int, do_run: bool,
            allow_tree_mismatch: bool = False,
            run_timeout: Optional[float] = None,
            with_baseline: bool = False) -> Dict[str, object]:
    base, head = parse_range(rev_range)
    started = time.time()

    git(clone, ["rev-parse", "--git-dir"])
    for rev in (base, head):
        git(clone, ["rev-parse", "--verify", "--quiet", "%s^{commit}" % rev])

    py_files, other_files = changed_files(clone, base, head)
    changed_paths = {entry.path for entry in py_files} | set(other_files)

    symbols, unparsed = removed_symbols(clone, base, head, py_files)
    attach_references(clone, symbols, changed_paths, limit, head)

    modules = sorted({entry.module for entry in py_files if entry.module})
    tests, _ = importing_tests(clone, modules, head)

    # A changed test file is selected for ITSELF. It used to be selected only
    # if it imported a changed module, so a range that edited a test file and
    # nothing else selected nothing at all - that was PR #134's fourth round,
    # where `gauntlet_view_smoke_test.py` changed alongside `index.html` and
    # this tool reported nothing to run.
    selected_paths = {t.path for t in tests}
    head_paths = set(tracked_paths(clone, head))
    for entry in py_files:
        if not is_test_path(entry.path) or entry.path in selected_paths:
            continue
        if entry.path not in head_paths:
            continue  # deleted by this range; there is nothing left to run
        tests.append(SelectedTest(path=entry.path, modules=["(changed test file)"]))
    tests.sort(key=lambda t: t.path)

    ci_paths, workflow_text = workflow_references(clone, head)
    for test in tests:
        dotted = module_path_for(test.path)
        test.in_ci = test.path in ci_paths or (
            dotted is not None and dotted in workflow_text
        )

    stale_ids = stale_workflow_test_ids(clone, head, workflow_text, tests)

    seconds_analysis = time.time() - started

    data: Dict[str, object] = {
        "clone": os.path.abspath(clone),
        "base": base,
        "head": head,
        "changed_python_files": [
            {"path": e.path, "module": e.module} for e in py_files
        ],
        "changed_other_files": other_files,
        "changed_modules": modules,
        "removed_symbols": [
            {
                "name": s.name,
                "file": s.file,
                "reference_count": s.hit_total,
                "external_reference_count": s.external_total,
                "hits": s.hits,
            }
            for s in symbols
        ],
        "importing_tests": [
            {"path": t.path, "modules": t.modules, "in_ci": t.in_ci} for t in tests
        ],
        "stale_workflow_test_ids": stale_ids,
        "commands": ["python -B %s" % t.path for t in tests],
        "unparsed_files": unparsed,
        "limits": LIMITS_TEXT,
        "seconds_analysis": round(seconds_analysis, 2),
    }

    matches, want, got = head_matches_worktree(clone, head)
    dirty = worktree_is_dirty(clone)
    data["worktree_at_head"] = matches and not dirty
    data["worktree_commit"] = got
    data["worktree_dirty"] = dirty
    data["untracked_python_files"] = untracked_python_files(clone)

    if do_run:
        if matches and dirty and not allow_tree_mismatch:
            raise CheckError(
                "--run executes the tests on disk. This clone is at %s, which is the head, "
                "but it has uncommitted changes to tracked files:\n%s\n"
                "  What would run is not %s. Commit, stash or discard them, or pass "
                "--run-on-current-tree to measure the tree as it stands."
                % (want, worktree_status(clone).rstrip() or "  (none reported)", head)
            )
        if not matches and not allow_tree_mismatch:
            raise CheckError(
                "--run executes the tests on disk, and this clone is checked out at %s, "
                "not at %s (%s).\n"
                "  Analysis above is correct - it reads git directly - but running here "
                "would measure a revision you did not ask about.\n"
                "  Check the clone out at the head first:\n"
                "      git -C %s checkout --detach %s\n"
                "  or pass --run-on-current-tree if you really mean to run what is on disk."
                % (got or "an unresolvable HEAD", want, head, clone, head)
            )
        run_started = time.time()
        sys.stderr.write("running %d selected tests...\n" % len(tests))
        data["run_results"] = run_tests(clone, tests, run_timeout)
        data["seconds_run"] = round(time.time() - run_started, 2)
        data["run_tree_was_head"] = matches and not dirty
        data["run_dirty_worktree"] = dirty
        if with_baseline:
            base_started = time.time()
            sys.stderr.write("running the same tests at %s for a baseline...\n" % base)
            data["run_baseline"] = run_at_baseline(clone, base, tests, run_timeout)
            data["seconds_baseline"] = round(time.time() - base_started, 2)
            classify_against_baseline(data["run_results"], data["run_baseline"])
            failure = (data["run_baseline"] or {}).get("error")
            data["run_caveat"] = (
                "baseline failed (%s) - verdicts are 'unknown'" % failure if failure else None
            )
        else:
            # Without a baseline a failure is not proof of a regression. Said
            # in the data as well as the report, so a machine consumer cannot
            # miss it, and every verdict is honestly 'unknown'.
            data["run_baseline"] = None
            classify_against_baseline(data["run_results"], None)
            data["run_caveat"] = (
                "single revision only - a failing test may already fail at %s. "
                "Pass --baseline to run it there and tell a regression from "
                "pre-existing red" % base
            )

    return data


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="propagation_check.py",
        description="Find stale references and the tests CI would run for a commit range.",
    )
    parser.add_argument("clone", help="path to the repository clone (read-only)")
    parser.add_argument("range", help="commit range, e.g. origin/main..HEAD")
    parser.add_argument("--run", action="store_true",
                        help="run the selected test files and report exit codes")
    parser.add_argument("--json", action="store_true",
                        help="emit machine-readable data instead of the report")
    parser.add_argument("--limit", type=int, default=10,
                        help="max reference hits printed per removed symbol (default 10)")
    parser.add_argument("--baseline", action="store_true",
                        help="with --run, also run the selected tests at <base> in a "
                             "throwaway worktree and label each result REGRESSION / "
                             "pre-existing / fixed. This is the only option that writes "
                             "to the clone (git worktree admin state), and it roughly "
                             "doubles the run time.")
    parser.add_argument("--run-timeout", type=float, default=None, metavar="SECONDS",
                        help="per-test wall clock for --run (default %d)"
                             % RUN_TIMEOUT_SECONDS)
    parser.add_argument("--run-on-current-tree", action="store_true",
                        help="with --run, allow running when the clone is NOT checked out "
                             "at the head of the range. The results then describe the tree "
                             "on disk, not the range you asked about.")
    args = parser.parse_args(argv)

    try:
        data = analyse(args.clone, args.range, args.limit, args.run,
                       allow_tree_mismatch=args.run_on_current_tree,
                       run_timeout=args.run_timeout,
                       with_baseline=args.baseline)
    except CheckError as exc:
        sys.stderr.write("propagation_check: %s\n" % exc)
        return 2

    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(build_report(data, args.limit))

    # Round 6, 2026-09-18: the three false-positive shapes round 5 found
    # (setattr parametrise loops, `Cls.x = fn` after the class body, and
    # method-adding class decorators) are now handled in class_bindings, so
    # a stale id fails the check again.
    if data.get("stale_workflow_test_ids"):
        return 1
    runs = data.get("run_results")
    if runs and any(r.get("status") != "pass" for r in runs):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
