"""Commit a reviewed follow-up contract revision for a task that has no GER packet (dry run by default).

    python apply_followup_revision.py --task NSC-049 --revised <json> --report <md> --reviewer <text> \
        --reason <text> [--commit]
        [--post-commit-check-report <path> --post-commit-check-commit <sha>]
        [--policy-filters-file <json>] [--drop-policy] [--journal <path>]

Preconditions (fail closed):
- Tasks/<ID>.yaml has no uncommitted change.
- The revised contract keeps the current file's top-level keys and invariant fields, raises contract_revision
  by exactly one, and leaves provenance.task_design_ger unchanged.
- The reviewer report names the first 16 hex characters of the revised file's sha256 and recommends
  commit_contract or commit_contract_then_decompose. --reviewer names who or what produced it (e.g. "Codex
  buildability check", "independent Claude Opus re-check"); it is recorded verbatim in provenance and the
  commit message. --reviewer must not be empty or whitespace-only.
- --post-commit-check-report/--post-commit-check-commit are optional but must be given together. They record
  this revision's provenance as also covering a post-commit Codex contract check (nsc-ger-orchestrator-guide.md,
  "The contract check") of an earlier commit: the report path, its sha256, the checked commit, and the
  verdict, which is parsed from the report's own last 'Final recommendation: commit_contract |
  commit_contract_then_decompose | revise' line (case-insensitive, markdown-tolerant). A report without that
  line, or a commit that does not exist, is not an ancestor of HEAD, or did not touch Tasks/<ID>.yaml, is a
  usage error.

Effects: key order is preserved; provenance gains a contract_followups record (reason, base and revised
hashes, reviewer recommendation, and the post-commit check record when given); RESOURCE_GROUPS.yaml is
reconciled exactly like apply_contract.py. Pipeline/TaskReviewAgent/authoritative_validation_policy.json: an
existing entry for the task is rebound to the new committed contract hash in the same commit, same rule as
contract_commit.py. --policy-filters-file sets or creates the entry; --drop-policy removes it for a revision
with no Unity gate; without an entry and without either flag the policy is untouched. Before committing, the
staged Tasks/<ID>.yaml blob hash must equal the hash just bound in the staged policy file, or all touched
files are restored and nothing is committed. taskcontrol validate and git diff --check must pass or all
touched files are restored; only those paths are staged and committed under the Contract Maintenance
.invalid identity. Never pushes.

The write is bracketed by MAIN-WRITE START/END journal markers (nsc-main-orchestrator-guide.md section 5):
it refuses when another role's START has no END in the last 30 minutes. --journal overrides the journal
path; without it, the live graph-lead journal is used only when the repo is the canonical checkout, so a
test or any other clone gets its own journal file inside its git dir instead (never the live one).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys

import apply_contract as ac
import main_write

IDENTITY = ["-c", "user.name=No Safe Circle Contract Maintenance",
            "-c", "user.email=contract-maintenance@nosafecircle.invalid"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--task", required=True)
    parser.add_argument("--revised", required=True, type=pathlib.Path)
    parser.add_argument("--report", required=True, type=pathlib.Path)
    parser.add_argument("--reviewer", required=True, help="Who or what produced --report, e.g. "
                        "'independent Claude Opus re-check' or 'Codex buildability check'")
    parser.add_argument("--legacy-report", action="store_true",
                        help="--report predates the JSON protocol and is read with the legacy "
                             "Markdown parser. A declaration by the caller, never inferred.")
    parser.add_argument("--reason", required=True)
    parser.add_argument("--post-commit-check-report", type=pathlib.Path,
                        help="With --post-commit-check-commit, records this revision's provenance as also "
                        "covering a post-commit Codex contract check of an earlier commit; the verdict is "
                        "parsed from the report's own 'Final recommendation:' line")
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
    parser.add_argument("--journal", type=pathlib.Path, default=None,
                        help="MAIN-WRITE START/END journal path (default: the live graph-lead journal for "
                        "the canonical checkout, otherwise a journal file inside this repo's own git dir)")
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()
    if args.journal is None:
        args.journal = main_write.default_journal(ac.REPO)
        if args.journal != main_write.JOURNAL:
            print(f"[PLAN] MAIN-WRITE journal (not the live one): {args.journal}")
    if not args.reviewer.strip():
        parser.error("--reviewer must not be empty")
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

    head = ac.git("rev-parse", "HEAD").stdout.decode().strip()
    original = path.read_bytes()
    if ac.git("show", f"HEAD:{rel}").stdout.replace(b"\r\n", b"\n") != original.replace(b"\r\n", b"\n"):
        raise SystemExit(f"{rel} has uncommitted changes; refusing")
    current = json.loads(original)
    revised_bytes = args.revised.read_bytes()
    proposed = json.loads(revised_bytes)
    revised_sha = ac.sha256(revised_bytes)

    report_bytes = args.report.read_bytes()

    def refuse(message: str):
        raise SystemExit(message)

    # The primary review of this followup revision. Same shared reader as the
    # round-08 recheck and the post-commit check: JSON bound to the exact revised
    # bytes by default, the old grep only when the caller declares --legacy-report.
    recommendation, report_protocol, _result = ac.read_imported_review(
        report_bytes,
        task_id=task_id,
        review_kind="ger",
        artifact_kind="ger_round_output",
        reviewed_sha256=revised_sha,
        legacy=args.legacy_report,
        legacy_reader=ac.final_recommendation,
        refuse=refuse)
    if recommendation not in ac.COMMITTABLE:
        raise SystemExit(f"reviewer recommendation is {recommendation!r}; not committing")

    if set(proposed) != set(current):
        raise SystemExit(f"top-level keys differ: missing {sorted(set(current) - set(proposed))}, extra {sorted(set(proposed) - set(current))}")
    for field in ac.INVARIANT_FIELDS:
        if proposed.get(field) != current.get(field):
            raise SystemExit(f"invariant field {field} changed")
    if proposed.get("contract_revision") != current.get("contract_revision", 0) + 1:
        raise SystemExit(f"contract_revision must be {current.get('contract_revision', 0) + 1}, got {proposed.get('contract_revision')}")
    if (proposed.get("provenance") or {}).get("task_design_ger") != (current.get("provenance") or {}).get("task_design_ger"):
        raise SystemExit("the revised contract must not change provenance.task_design_ger")

    merged = {key: proposed[key] for key in current}
    provenance = dict(merged.get("provenance") or {})
    followup_entry = {
        "date": dt.datetime.now(dt.timezone.utc).date().isoformat(), "reason": args.reason, "source_head": head,
        "previous_contract_revision": current.get("contract_revision"),
        "base_contract_sha256": ac.sha256(original), "revised_contract_sha256": revised_sha,
        "review": args.reviewer, "review_report_sha256": ac.sha256(report_bytes),
        "recheck_recommendation": recommendation}
    if post_commit_check:
        followup_entry["post_commit_check"] = post_commit_check
    provenance["contract_followups"] = list(provenance.get("contract_followups") or []) + [followup_entry]
    merged["provenance"] = provenance
    changed = sorted(key for key in current if current.get(key) != merged.get(key))
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

    touched = [rel] + ([groups_rel] if group_changes else []) + ([policy_rel] if policy_bytes else [])
    if ac.git("status", "--porcelain=v1", "--", *touched).stdout.decode().strip():
        raise SystemExit("target paths already have uncommitted changes")
    if ac.git("diff", "--cached", "--name-only").stdout.decode().strip():
        raise SystemExit("the index already has staged paths; refusing to commit")

    def restore() -> None:
        path.write_bytes(original)
        groups_path.write_bytes(groups_original)
        policy_path.write_bytes(policy_original)

    if ac.git("rev-parse", "HEAD").stdout.decode().strip() != head:
        raise SystemExit("HEAD moved since planning; rerun")
    main_write.start(f"{task_id} follow-up contract revision {merged['contract_revision']}", head, journal=args.journal)
    try:
        commit = write_and_commit(args, task_id, rel, path, merged, changed, recommendation, touched, restore,
                                  group_changes, groups_path, groups_bytes, policy_path, policy_bytes, blob_sha,
                                  head, b"\r\n" in original)
    except BaseException as error:
        main_write.end(ac.git("rev-parse", "HEAD").stdout.decode().strip(),
                       f"aborted, nothing committed ({error})", journal=args.journal)
        raise
    main_write.end(commit, f"{task_id} rev {merged['contract_revision']}; taskcontrol validate PASS; not pushed",
                   journal=args.journal)
    return 0


def write_and_commit(args, task_id, rel, path, merged, changed, recommendation, touched, restore, group_changes,
                     groups_path, groups_bytes, policy_path, policy_bytes, blob_sha, head, crlf) -> str:
    # G15b round 4: one failed write must not leave the earlier ones on disk.
    try:
        path.write_bytes(ac.serialize(merged, crlf))
        if group_changes:
            groups_path.write_bytes(groups_bytes)
        if policy_bytes:
            policy_path.write_bytes(policy_bytes)
    except OSError as error:
        restore()
        raise SystemExit(f"writing {touched} failed; restored: {error}") from error
    validate = subprocess.run([sys.executable, "-B", "Pipeline/TaskGraph/taskcontrol.py", "validate"], cwd=str(ac.REPO),
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"},
                              creationflags=subprocess.CREATE_NO_WINDOW)
    print(validate.stdout.strip()[-300:])
    if validate.returncode != 0 or "PASS" not in validate.stdout:
        restore()
        raise SystemExit(f"taskcontrol validate failed; restored {touched}:\n{(validate.stdout + validate.stderr).strip()[-1200:]}")
    if ac.git("diff", "--check", "--", *touched, check=False).returncode != 0:
        restore()
        raise SystemExit(f"git diff --check failed; restored {touched}")
    # Everything from here on (including writing the commit message) is inside the protected region: a
    # failure at any step must restore the task/groups/policy files and unstage, not just the git steps
    # after the message file already exists on disk.
    try:
        message_path = args.revised.parent / "COMMIT_MESSAGE.txt"
        message_path.write_text(
            f"TaskGraph: follow-up contract revision {merged['contract_revision']} for {task_id}\n\n"
            f"{args.reason}\n"
            f"{args.reviewer} recommended {recommendation}.\n"
            f"Changed fields: {', '.join(changed)}.\n"
            + (("Validation policy entry removed: this revision has no Unity test gate.\n" if args.drop_policy
                else f"Validation policy rebound to contract sha256 {blob_sha}.\n") if policy_bytes else "") + "\n"
            "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>\n", encoding="utf-8")
        ac.git("add", "--", *touched)
        staged = sorted(line for line in ac.git("diff", "--cached", "--name-only").stdout.decode().splitlines() if line)
        if staged != sorted(touched):
            raise RuntimeError(f"unexpected staged paths {staged}")
        if policy_bytes and ac.sha256(ac.git("show", f":{rel}").stdout) != blob_sha:
            raise RuntimeError("staged contract blob hash differs from the rebound policy hash")
        ac.git(*IDENTITY, "commit", "-F", str(message_path))
    except (SystemExit, RuntimeError, OSError) as exc:
        # G15b round 4: reset the whole index, not just these paths. Both tools refuse to start with
        # anything staged, and a path git staged under a different spelling (a case variant of an
        # existing folder) would survive a pathspec reset.
        ac.git("reset", "-q")
        restore()
        raise SystemExit(f"commit failed; unstaged and restored {touched}: {exc}") from exc
    commit = ac.git("rev-parse", "HEAD").stdout.decode().strip()
    print(f"[DONE] {task_id} follow-up contract commit {commit} (parent {head}; files {touched}); not pushed")
    return commit


if __name__ == "__main__":
    raise SystemExit(main())
