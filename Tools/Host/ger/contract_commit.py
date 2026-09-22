"""Commit any validated revised contract with review: none (dry run by default).

    python -B contract_commit.py --task NSC-077 --revised <json> --reason <text> [--commit]
        [--post-commit-check-report <path> --post-commit-check-commit <sha>]
        [--policy-filters-file <json>] [--drop-policy] [--review <text>]
        [--extra-file REPO_PATH=SOURCE ...] [--journal <path>]

The supported ger-tools committer for a full design revision (e.g. acceptance-criteria text), a
superseded_by supersede, or a contract_disposition change, per the 2026-09-17 contract check
(nsc-ger-orchestrator-guide.md, "The contract check"): committing is never blocked, and taskcontrol
validate is the only gate. Design revisions get a Codex buildability check after the commit, not before.

Steps:
- Tasks/<ID>.yaml must match HEAD; nothing may be staged; the target paths must be clean.
- id, parent, schema_version and reconciliation_key stay the same and contract_revision rises by exactly one.
- The contract is written in the file's own key order (an added superseded_by goes right after
  contract_disposition) and line endings; provenance gains a contract_followups record.
- taskcontrol validate refuses an invalid supersede target (missing or self); this script adds no separate
  check for that.
- RESOURCE_GROUPS.yaml is reconciled with apply_contract.py's helpers.
- Pipeline/TaskReviewAgent/authoritative_validation_policy.json: an existing entry for the task is rebound to
  the new committed contract hash in the same commit (the pipeline refuses a stale entry).
  --policy-filters-file (a JSON object of platform -> Unity test filter, in platform order) replaces the
  entry's platforms and filters, or creates the entry. --drop-policy removes the entry for a revision with no
  Unity gate. Without an entry and without either flag the policy is untouched. Before committing, the staged
  Tasks/<ID>.yaml blob hash must equal the hash just bound in the staged policy file, or both files are
  restored and nothing is committed.
- taskcontrol validate and git diff --check must pass, or all touched files are restored.
- Exactly those paths are staged and committed as No Safe Circle Contract Maintenance <contract-maintenance@
  nosafecircle.invalid>. If staging or the commit itself then fails (e.g. a hook rejects it), touched files
  are restored and unstaged and the script exits nonzero. Never pushes.
- The write is bracketed by MAIN-WRITE START/END journal markers (nsc-main-orchestrator-guide.md section 5):
  it refuses when another role's START has no END in the last 30 minutes. --journal overrides the journal
  path; without it, the live graph-lead journal is used only when the repo is the canonical checkout, so a
  test or any other clone gets its own journal file inside its git dir instead (never the live one).

--review TEXT is a free-text review label recorded in provenance and the commit message (e.g. "post-commit
Codex closure review pending" or "grep review only"). Default, unchanged from before this flag existed:
"none; no pre-commit review, design revisions get a post-commit Codex contract check (2026-09-17)".

--extra-file REPO_PATH=SOURCE adds a brand-new repository file (not present at HEAD or in the working
tree) with SOURCE's exact bytes, staged and committed alongside the contract; repeatable. SOURCE must be
LF (no CRLF bytes). Refuses if REPO_PATH already exists anywhere, if REPO_PATH is absolute or escapes the
repo, or if the staged bytes end up differing from SOURCE.

--post-commit-check-report/--post-commit-check-commit are optional but must be given together. They record
this revision's provenance as also covering a post-commit Codex contract check (nsc-ger-orchestrator-guide.md,
"The contract check") of an earlier commit: the report path, its sha256, the checked commit, and the
verdict, which is parsed from the report's own last 'Final recommendation: commit_contract |
commit_contract_then_decompose | revise' line (case-insensitive, markdown-tolerant). A report without that
line, or a commit that does not exist, is not an ancestor of HEAD, or did not touch Tasks/<ID>.yaml, is a
usage error.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
import unicodedata

import apply_contract as ac
import main_write

IDENTITY = ["-c", "user.name=No Safe Circle Contract Maintenance",
            "-c", "user.email=contract-maintenance@nosafecircle.invalid"]

DEFAULT_REVIEW = "none; no pre-commit review, design revisions get a post-commit Codex contract check (2026-09-17)"


RESERVED_DEVICE_NAMES = frozenset({"con", "prn", "aux", "nul"}
                                  | {f"com{index}" for index in range(1, 10)}
                                  | {f"lpt{index}" for index in range(1, 10)})


def repo_path_is_safe(repo_path: str) -> bool:
    """G15b round 3, hardened in rounds 4 and 5: an --extra-file target must stay inside the repository.

    Refuses drive-qualified (C:/x, c:x), rooted, UNC and backslash paths, any colon (drives and NTFS
    streams), empty, '.' or '..' parts, anything under .git in any case (including its 8.3 short name and
    Unicode lookalikes that NFKC-fold to it), Windows device names, wildcard and control characters,
    trailing dots or spaces, a part whose spelling or case differs from the folder on disk, a part that
    is a junction or symlink, and anything that resolves outside the repo or inside its git dir.

    A path inside .git matters because a hook written there runs during the tool's own git commands, and
    a successful commit never restores anything, so the hook would stay. A spelling that differs from the
    folder on disk matters because git stages it under the real spelling, which the staged check compares.
    """
    if not repo_path or "\\" in repo_path or ":" in repo_path or repo_path.startswith("/"):
        return False
    if any(character in repo_path for character in '<>"|?*$') or any(ord(c) < 32 for c in repo_path):
        return False
    parts = repo_path.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return False
    for part in parts:
        folded = unicodedata.normalize("NFKC", part).casefold().rstrip(" ")
        if folded == ".git" or "~" in part:
            return False
        if folded.split(".")[0] in RESERVED_DEVICE_NAMES:
            return False
        if part != part.rstrip(". "):
            return False
    windows = pathlib.PureWindowsPath(repo_path)
    if windows.drive or windows.root:
        return False
    # Every existing part must be the real folder, not a junction, a symlink or another spelling of it.
    current = ac.REPO
    for part in parts:
        current = current / part
        # str(), because WindowsPath equality ignores case and would accept another spelling.
        if current.exists() and str(current.resolve()) != str(current.parent.resolve() / part):
            return False
    repo_root = ac.REPO.resolve()
    resolved = (ac.REPO / repo_path).resolve()
    if not resolved.is_relative_to(repo_root):
        return False
    git_dir = pathlib.Path(ac.git("rev-parse", "--absolute-git-dir").stdout.decode().strip()).resolve()
    return not resolved.is_relative_to(git_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--task", required=True)
    parser.add_argument("--revised", required=True, type=pathlib.Path)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--post-commit-check-report", type=pathlib.Path,
                        help="With --post-commit-check-commit, records this revision's provenance as also "
                        "covering a post-commit Codex contract check of an earlier commit. Pass the "
                        "reviewer's .result.json, which must have its job record beside it; "
                        "the verdict is the recommendation that result DECLARES. A .report.md "
                        "is a rendered view and is refused.")
    parser.add_argument("--post-commit-check-commit", metavar="SHA")
    parser.add_argument("--post-commit-check-import", metavar="WHO",
                        help="the report was handed over by a person rather than produced "
                             "by a job here; names who carried it, and is recorded as "
                             "import provenance. Without it the report must have its job "
                             "record beside it.")
    parser.add_argument("--post-commit-check-legacy", action="store_true",
                        help="the report predates the JSON closure protocol and is read "
                             "with the legacy Markdown parser. A declaration, never "
                             "inferred: a new-format result that fails to validate is "
                             "refused, never retried through the old reader.")
    parser.add_argument("--policy-filters-file", type=pathlib.Path,
                        help="JSON object mapping EditMode/PlayMode to a Unity test filter; sets or creates "
                        "the task's authoritative_validation_policy.json entry")
    parser.add_argument("--drop-policy", action="store_true",
                        help="remove the task's validation policy entry (the revision has no Unity test gate)")
    parser.add_argument("--review", default=DEFAULT_REVIEW,
                        help="free-text review label recorded in provenance and the commit message")
    parser.add_argument("--extra-file", action="append", default=[],
                        help="REPO_PATH=SOURCE: add a new repository file (absent at HEAD) with SOURCE's "
                        "exact bytes in the same commit")
    parser.add_argument("--role", default=None,
                        help="the role writing to main, e.g. 'GER Agent'. Falls back to "
                             "NSC_ROLE. Required: the one-writer guard compares open "
                             "writes against it, and a default is what made that guard "
                             "compare every role against itself until 2026-09-22.")
    parser.add_argument("--journal", type=pathlib.Path, default=None,
                        help="MAIN-WRITE START/END journal path (default: the live graph-lead journal for "
                        "the canonical checkout, otherwise a journal file inside this repo's own git dir)")
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()
    if args.journal is None:
        args.journal = main_write.default_journal(ac.REPO)
        if args.journal != main_write.JOURNAL:
            print(f"[PLAN] MAIN-WRITE journal (not the live one): {args.journal}")
    post_commit_flags = (args.post_commit_check_report, args.post_commit_check_commit)
    if any(post_commit_flags) and not all(post_commit_flags):
        parser.error("--post-commit-check-report and --post-commit-check-commit must be given together")
    task_id = args.task
    post_commit_check = None
    if args.post_commit_check_report:
        post_commit_check = ac.resolve_post_commit_check(
            args.post_commit_check_report, args.post_commit_check_commit, task_id, parser.error,
            legacy=args.post_commit_check_legacy,
            import_source=args.post_commit_check_import)
    rel = f"Tasks/{task_id}.yaml"
    path = ac.REPO / rel
    extras = []
    for spec in args.extra_file:
        repo_path, _, source = spec.partition("=")
        if not source or not repo_path_is_safe(repo_path):
            raise SystemExit(
                f"bad --extra-file {spec!r}; REPO_PATH must be a new file's path inside the repository: "
                "forward slashes, spelled exactly as the folders on disk are (including case); no drive, "
                "colon, `$`, wildcard or control characters; no empty, '.' or '..' parts; no trailing dot "
                "or space; nothing inside .git, through a junction or symlink, or named after a Windows "
                "device (CON, NUL, COM1...)")
        if ac.git("cat-file", "-e", f"HEAD:{repo_path}", check=False).returncode == 0:
            raise SystemExit(f"--extra-file {repo_path} already exists at HEAD; this option only adds new files")
        if (ac.REPO / repo_path).exists():
            raise SystemExit(f"--extra-file {repo_path} already exists in the working tree; refusing")
        data = pathlib.Path(source).read_bytes()
        if b"\r\n" in data:
            raise SystemExit(f"--extra-file source {source} has CRLF line endings; supply LF bytes")
        extras.append((repo_path, data))
        print(f"[PLAN] extra file {repo_path} ({len(data)} bytes, sha256 {ac.sha256(data)})")

    head = ac.git("rev-parse", "HEAD").stdout.decode().strip()
    original = path.read_bytes()
    if ac.git("show", f"HEAD:{rel}").stdout.replace(b"\r\n", b"\n") != original.replace(b"\r\n", b"\n"):
        raise SystemExit(f"{rel} differs from HEAD; refusing")
    current = json.loads(original)
    revised_bytes = args.revised.read_bytes()
    proposed = json.loads(revised_bytes)
    if proposed.get("id") != task_id:
        raise SystemExit(f"the revised contract is for {proposed.get('id')!r}, not {task_id}")
    for field in ac.INVARIANT_FIELDS:
        if proposed.get(field) != current.get(field):
            raise SystemExit(f"invariant field {field} changed")
    if proposed.get("contract_revision") != current.get("contract_revision", 0) + 1:
        raise SystemExit(f"contract_revision must be {current.get('contract_revision', 0) + 1}, got {proposed.get('contract_revision')}")
    added = set(proposed) - set(current)
    missing = set(current) - set(proposed)
    if missing or not added <= {"superseded_by"}:
        raise SystemExit(f"top-level keys differ: missing {sorted(missing)}, extra {sorted(added)}")

    merged = {}
    for key in current:
        merged[key] = proposed[key]
        if key == "contract_disposition" and "superseded_by" in added:
            merged["superseded_by"] = proposed["superseded_by"]
    provenance = dict(merged.get("provenance") or {})
    followup_entry = {
        "date": dt.datetime.now(dt.timezone.utc).date().isoformat(), "reason": args.reason, "source_head": head,
        "previous_contract_revision": current.get("contract_revision"),
        "base_contract_sha256": ac.sha256(original), "revised_contract_sha256": ac.sha256(revised_bytes),
        "review": args.review}
    if post_commit_check:
        followup_entry["post_commit_check"] = post_commit_check
    provenance["contract_followups"] = list(provenance.get("contract_followups") or []) + [followup_entry]
    merged["provenance"] = provenance
    changed = sorted(key for key in merged if current.get(key) != merged.get(key))
    print(f"[PLAN] {task_id}: revision {current.get('contract_revision')} -> {merged['contract_revision']} at HEAD {head}")
    print(f"[PLAN] changed fields: {changed}")

    groups_rel = "Pipeline/TaskGraph/RESOURCE_GROUPS.yaml"
    groups_path = ac.REPO / groups_rel
    groups_original = groups_path.read_bytes()
    groups_crlf = b"\r\n" in groups_original
    groups_data = json.loads(groups_original)
    groups_canonical = ac.serialize(groups_data, groups_crlf) == groups_original
    all_tasks = [merged if json.loads(f.read_bytes()).get("id") == task_id else json.loads(f.read_bytes())
                 for f in sorted((ac.REPO / "Tasks").glob("NSC-*.yaml"))]
    group_changes = ac.reconcile_resource_groups(groups_data["resource_groups"], all_tasks)
    for change in group_changes:
        after = change["after"]
        entry = {"reconciliation_keys": after["reconciliation_keys"], "resource_key": after["resource_key"],
                 "work_ids": after["work_ids"]}
        if change["change_type"] == "updated":
            index = next(i for i, group in enumerate(groups_data["resource_groups"]) if group["resource_key"] == after["resource_key"])
            groups_data["resource_groups"][index] = entry
        else:
            groups_data["resource_groups"].append(entry)
        print(f"[PLAN] resource group {change['change_type']}: {after['resource_key']} -> {after['work_ids']}")
    groups_bytes = None
    if group_changes:
        groups_bytes = (ac.serialize(groups_data, groups_crlf) if groups_canonical
                        else ac.append_created_groups(groups_original, groups_data, group_changes, groups_crlf))

    policy_rel = "Pipeline/TaskReviewAgent/authoritative_validation_policy.json"
    policy_path = ac.REPO / policy_rel
    policy_original = policy_path.read_bytes()
    policy_head = ac.git("show", f"HEAD:{policy_rel}").stdout
    if policy_head.replace(b"\r\n", b"\n") != policy_original.replace(b"\r\n", b"\n"):
        if args.commit:
            raise SystemExit(f"{policy_rel} differs from HEAD; refusing")
        # G15b round 3: a dry run only previews. Plan from HEAD's copy and say that a commit refuses.
        print(f"[PLAN] WARNING: {policy_rel} differs from HEAD; planning from HEAD's copy. A --commit run refuses.")
        policy_original = policy_head
    policy_data = json.loads(policy_original)
    policy_filters = (json.loads(args.policy_filters_file.read_bytes().decode("utf-8"))
                      if args.policy_filters_file else None)
    ac.validate_policy_filters(policy_filters)
    blob_sha = ac.contract_blob_sha256(merged)
    policy_bytes, policy_message = ac.plan_policy_rebind(
        policy_data, b"\r\n" in policy_original, task_id, blob_sha, policy_filters, args.drop_policy)
    if policy_message:
        print(f"[PLAN] {policy_message}")

    if not args.commit:
        print("[DRY RUN] no file written")
        return 0

    touched = ([rel] + ([groups_rel] if group_changes else []) + ([policy_rel] if policy_bytes else [])
               + [extra_path for extra_path, _ in extras])
    if ac.git("status", "--porcelain=v1", "--", *touched).stdout.decode().strip():
        raise SystemExit("target paths already have uncommitted changes")
    if ac.git("diff", "--cached", "--name-only").stdout.decode().strip():
        raise SystemExit("the index already has staged paths; refusing to commit")

    # G15b round 5: folders this run creates for an extra file are removed again when it fails, and one
    # failing step no longer skips the rest of the restore.
    created_directories = []
    for extra_path, _ in extras:
        parent = (ac.REPO / extra_path).parent
        while not parent.exists() and parent != ac.REPO:
            if parent not in created_directories:
                created_directories.append(parent)
            parent = parent.parent

    def restore() -> None:
        problems = []
        for step in ([lambda: path.write_bytes(original),
                      lambda: groups_path.write_bytes(groups_original),
                      lambda: policy_path.write_bytes(policy_original)]
                     + [(lambda extra=extra_path: (ac.REPO / extra).unlink(missing_ok=True))
                        for extra_path, _ in extras]
                     + [(lambda directory=directory: directory.rmdir())
                        for directory in sorted(created_directories, key=lambda p: len(p.parts), reverse=True)]):
            try:
                step()
            except OSError as error:
                problems.append(str(error))
        if problems:
            print(f"[WARN] restore incomplete: {'; '.join(problems)}")

    if ac.git("rev-parse", "HEAD").stdout.decode().strip() != head:
        raise SystemExit("HEAD moved since planning; rerun")
    with main_write.transaction(f"{task_id} contract revision {merged['contract_revision']}", head, role=args.role, journal=args.journal, repo=ac.REPO, touched=touched,
                                expected_files={rel: original, groups_rel: groups_original,
                                                policy_rel: policy_original}):
        commit = write_and_commit(args, task_id, rel, path, merged, changed, touched, restore, group_changes,
                                  groups_path, groups_bytes, policy_path, policy_bytes, blob_sha, head,
                                  b"\r\n" in original, extras)
    return 0


def write_and_commit(args, task_id, rel, path, merged, changed, touched, restore, group_changes, groups_path,
                     groups_bytes, policy_path, policy_bytes, blob_sha, head, crlf, extras) -> str:
    # G15b round 4: one failed write must not leave the earlier ones on disk.
    try:
        path.write_bytes(ac.serialize(merged, crlf))
        if group_changes:
            groups_path.write_bytes(groups_bytes)
        if policy_bytes:
            policy_path.write_bytes(policy_bytes)
        for extra_path, data in extras:
            target = ac.REPO / extra_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    except OSError as error:
        restore()
        raise SystemExit(f"writing {touched} failed; restored: {error}") from error
    validate = main_write.run_process([sys.executable, "-B", "Pipeline/TaskGraph/taskcontrol.py", "validate"], cwd=str(ac.REPO),
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"},
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    print(validate.stdout.strip()[-300:])
    if validate.returncode != 0 or "PASS" not in validate.stdout:
        restore()
        raise SystemExit(f"taskcontrol validate failed; restored {touched}:\n{(validate.stdout + validate.stderr).strip()[-1200:]}")
    if ac.git("diff", "--check", "--", *touched, check=False).returncode != 0:
        restore()
        raise SystemExit(f"git diff --check failed; restored {touched}")
    # Everything from here on (including writing the commit message) is inside the protected region: a
    # failure at any step must restore the task/groups/policy/extra files and unstage, not just the git
    # steps after the message file already exists on disk.
    try:
        message_path = args.revised.parent / f"COMMIT_MESSAGE.{task_id}.txt"
        message_path.write_text(
            f"TaskGraph: owner contract revision {merged['contract_revision']} for {task_id}\n\n"
            f"{args.reason}\n"
            f"Review: {args.review}.\n"
            f"Changed fields: {', '.join(changed)}.\n"
            + (("Validation policy entry removed: this revision has no Unity test gate.\n" if args.drop_policy
                else f"Validation policy rebound to contract sha256 {blob_sha}.\n") if policy_bytes else "")
            + "".join(f"Adds {extra_path} (sha256 {ac.sha256(data)}).\n" for extra_path, data in extras) + "\n"
            "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>\n", encoding="utf-8")
        ac.git("add", "--", *touched)
        staged = sorted(line for line in ac.git("diff", "--cached", "--name-only").stdout.decode().splitlines() if line)
        if staged != sorted(touched):
            raise RuntimeError(f"unexpected staged paths {staged}")
        if policy_bytes and ac.sha256(ac.git("show", f":{rel}").stdout) != blob_sha:
            raise RuntimeError("staged contract blob hash differs from the rebound policy hash")
        for extra_path, data in extras:
            if ac.sha256(ac.git("show", f":{extra_path}").stdout) != ac.sha256(data):
                raise RuntimeError(f"staged {extra_path} differs from its source bytes")
        ac.git(*IDENTITY, "commit", "-F", str(message_path))
    except main_write.MutationChildUncertain:
        raise
    except (SystemExit, RuntimeError, OSError) as exc:
        if ac.git("rev-parse", "HEAD").stdout.decode().strip() != head:
            raise  # preserve a completed commit when a later step reports failure
        # G15b round 4: reset the whole index, not just these paths. Both tools refuse to start with
        # anything staged, and a path git staged under a different spelling (a case variant of an
        # existing folder) would survive a pathspec reset.
        ac.git("reset", "-q")
        restore()
        raise SystemExit(f"commit failed; unstaged and restored {touched}: {exc}") from exc
    commit = ac.git("rev-parse", "HEAD").stdout.decode().strip()
    files = ac.git("show", "--name-only", "--format=", "HEAD").stdout.decode().split()
    print(f"[DONE] {task_id} contract commit {commit} (parent {head}; files {files}); not pushed")
    return commit


if __name__ == "__main__":
    raise SystemExit(main())
