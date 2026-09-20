"""Commit one owner contract revision by the GER_AGENT_RUNBOOK.md "Contract edit" steps (dry run by default).

    python -B runbook_contract_commit.py --task NSC-077 --revised <json> --reason <text> [--commit]

Vincent, 2026-09-16: no re-check gate; taskcontrol validate is the only check. Steps:
- Tasks/<ID>.yaml must match HEAD; nothing may be staged; the target paths must be clean.
- id, parent, schema_version and reconciliation_key stay the same and contract_revision rises by exactly one.
- The contract is written in the file's own key order (an added superseded_by goes right after
  contract_disposition) and line endings; provenance gains a contract_followups record.
- RESOURCE_GROUPS.yaml is reconciled with apply_contract.py's helpers.
- taskcontrol validate and git diff --check must pass, or both files are restored.
- Pipeline/TaskReviewAgent/authoritative_validation_policy.json: an existing entry for the task is rebound to
  the new committed contract hash in the same commit (the pipeline refuses a stale entry). --policy-filters-file
  (a JSON object of platform -> Unity test filter, in platform order) replaces the entry's platforms and
  filters, or creates the entry. Without an entry and without the file the policy is untouched.
- Exactly those paths are staged and committed as No Safe Circle Contract Maintenance (.invalid). Never pushes.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, r"C:\nscrev\ger-tools")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import apply_contract as ac  # noqa: E402  (helpers only: git, sha256, serialize, resource-group reconciliation)
import main_write  # noqa: E402  (journal MAIN-WRITE START/END markers)

IDENTITY = ["-c", "user.name=No Safe Circle Contract Maintenance",
            "-c", "user.email=contract-maintenance@nosafecircle.invalid"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--task", required=True)
    parser.add_argument("--revised", required=True, type=pathlib.Path)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--policy-filters-file", type=pathlib.Path)
    parser.add_argument("--drop-policy", action="store_true",
                        help="remove the task's validation policy entry (the revision has no Unity test gate)")
    parser.add_argument("--review", default="post-commit Codex contract check (tiered rule, 2026-09-17)")
    parser.add_argument("--extra-file", action="append", default=[],
                        help="REPO_PATH=SOURCE: add a new repository file (absent at HEAD) with SOURCE's exact bytes in the same commit")
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()
    task_id = args.task
    rel = f"Tasks/{task_id}.yaml"
    path = ac.REPO / rel
    extras = []
    for spec in args.extra_file:
        repo_path, _, source = spec.partition("=")
        if not repo_path or not source or repo_path.startswith(("/", "\\")) or ".." in repo_path.replace("\\", "/").split("/"):
            raise SystemExit(f"bad --extra-file {spec!r}; use REPO_PATH=SOURCE with a relative repository path")
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
    provenance["contract_followups"] = list(provenance.get("contract_followups") or []) + [{
        "date": dt.datetime.now(dt.timezone.utc).date().isoformat(), "reason": args.reason, "source_head": head,
        "previous_contract_revision": current.get("contract_revision"),
        "base_contract_sha256": ac.sha256(original), "revised_contract_sha256": ac.sha256(revised_bytes),
        "review": args.review}]
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
    if ac.git("show", f"HEAD:{policy_rel}").stdout.replace(b"\r\n", b"\n") != policy_original.replace(b"\r\n", b"\n"):
        raise SystemExit(f"{policy_rel} differs from HEAD; refusing")
    policy_data = json.loads(policy_original)
    policy_filters = (json.loads(args.policy_filters_file.read_bytes().decode("utf-8"))
                      if args.policy_filters_file else None)
    if policy_filters is not None and (not isinstance(policy_filters, dict) or not policy_filters or any(
            platform not in ("EditMode", "PlayMode") or not isinstance(value, str) or not value.strip()
            for platform, value in policy_filters.items())):
        raise SystemExit("--policy-filters-file must map EditMode/PlayMode to non-empty filter strings")
    blob_sha = ac.sha256(ac.serialize(merged, False))  # git stores LF bytes (core.autocrlf)
    policy_entry = policy_data["tasks"].get(task_id)
    policy_bytes = None
    if args.drop_policy:
        if policy_filters is not None or policy_entry is None:
            raise SystemExit("--drop-policy needs an existing entry and no --policy-filters-file")
        del policy_data["tasks"][task_id]
        policy_bytes = ac.serialize(policy_data, b"\r\n" in policy_original)
        print(f"[PLAN] validation policy entry removed for {task_id} (was {policy_entry['test_filters']})")
    elif policy_entry is not None or policy_filters is not None:
        entry = dict(policy_entry or {"authority": "committed_task_specific_authoritative_validation_policy"})
        rebound = {"task_contract_sha256": blob_sha}
        if policy_filters is not None:
            rebound["required_test_platforms"] = list(policy_filters)
            rebound["test_filters"] = dict(policy_filters)
        ordered = {"task_contract_sha256": None, "required_test_platforms": None, "test_filters": None}
        ordered.update(entry)
        ordered.update(rebound)
        policy_data["tasks"][task_id] = ordered
        policy_bytes = ac.serialize(policy_data, b"\r\n" in policy_original)
        print(f"[PLAN] validation policy {'rebound' if policy_entry else 'created'} for {task_id}: "
              f"{(policy_entry or {}).get('task_contract_sha256', '-')[:16]} -> {blob_sha[:16]}; "
              f"filters {ordered['test_filters']}")
    if not args.commit:
        print("[DRY RUN] no file written")
        return 0

    touched = ([rel] + ([groups_rel] if group_changes else []) + ([policy_rel] if policy_bytes else [])
               + [repo_path for repo_path, _ in extras])
    if ac.git("status", "--porcelain=v1", "--", *touched).stdout.decode().strip():
        raise SystemExit("target paths already have uncommitted changes")
    if ac.git("diff", "--cached", "--name-only").stdout.decode().strip():
        raise SystemExit("the index already has staged paths; refusing to commit")
    args.extras = extras

    def restore() -> None:
        path.write_bytes(original)
        groups_path.write_bytes(groups_original)
        policy_path.write_bytes(policy_original)
        for repo_path, _ in extras:
            (ac.REPO / repo_path).unlink(missing_ok=True)

    if ac.git("rev-parse", "HEAD").stdout.decode().strip() != head:
        raise SystemExit("HEAD moved since planning; rerun")
    main_write.start(f"{task_id} contract revision {merged['contract_revision']}", head)
    try:
        commit = write_and_commit(args, task_id, rel, path, merged, changed, touched, restore, group_changes,
                                  groups_path, groups_bytes, policy_path, policy_bytes, blob_sha, head,
                                  b"\r\n" in original)
    except BaseException as error:
        main_write.end(ac.git("rev-parse", "HEAD").stdout.decode().strip(), f"aborted, nothing committed ({error})")
        raise
    main_write.end(commit, f"{task_id} rev {merged['contract_revision']}; taskcontrol validate PASS; not pushed")
    return 0


def write_and_commit(args, task_id, rel, path, merged, changed, touched, restore, group_changes, groups_path,
                     groups_bytes, policy_path, policy_bytes, blob_sha, head, crlf) -> str:
    path.write_bytes(ac.serialize(merged, crlf))
    if group_changes:
        groups_path.write_bytes(groups_bytes)
    if policy_bytes:
        policy_path.write_bytes(policy_bytes)
    for repo_path, data in args.extras:
        target = ac.REPO / repo_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    validate = subprocess.run([sys.executable, "-B", "Pipeline/TaskGraph/taskcontrol.py", "validate"], cwd=str(ac.REPO),
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"})
    print(validate.stdout.strip()[-300:])
    if validate.returncode != 0 or "PASS" not in validate.stdout:
        restore()
        raise SystemExit(f"taskcontrol validate failed; restored {touched}:\n{(validate.stdout + validate.stderr).strip()[-1200:]}")
    if ac.git("diff", "--check", "--", *touched, check=False).returncode != 0:
        restore()
        raise SystemExit(f"git diff --check failed; restored {touched}")
    ac.git("add", "--", *touched)
    staged = sorted(line for line in ac.git("diff", "--cached", "--name-only").stdout.decode().splitlines() if line)
    if staged != sorted(touched):
        ac.git("reset", "-q", "--", *touched)
        restore()
        raise SystemExit(f"unexpected staged paths {staged}; unstaged and restored")
    if policy_bytes and ac.sha256(ac.git("show", f":{rel}").stdout) != blob_sha:
        ac.git("reset", "-q", "--", *touched)
        restore()
        raise SystemExit("staged contract blob hash differs from the rebound policy hash; unstaged and restored")
    for repo_path, data in args.extras:
        if ac.sha256(ac.git("show", f":{repo_path}").stdout) != ac.sha256(data):
            ac.git("reset", "-q", "--", *touched)
            restore()
            raise SystemExit(f"staged {repo_path} differs from its source bytes; unstaged and restored")
    message_path = args.revised.resolve().parent / f"COMMIT_MESSAGE.{task_id}.txt"
    message_path.write_text(
        f"TaskGraph: owner contract revision {merged['contract_revision']} for {task_id}\n\n"
        f"{args.reason}\n"
        f"Review: {args.review}.\n"
        f"Changed fields: {', '.join(changed)}.\n"
        + (("Validation policy entry removed: this revision has no Unity test gate.\n" if args.drop_policy
            else f"Validation policy rebound to contract sha256 {blob_sha}.\n") if policy_bytes else "")
        + "".join(f"Adds {repo_path} (sha256 {ac.sha256(data)}).\n" for repo_path, data in args.extras) + "\n"
        "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>\n", encoding="utf-8")
    ac.git(*IDENTITY, "commit", "-F", str(message_path))
    commit = ac.git("rev-parse", "HEAD").stdout.decode().strip()
    files = ac.git("show", "--name-only", "--format=", "HEAD").stdout.decode().split()
    print(f"[DONE] {task_id} contract commit {commit} (parent {head}; files {files}); not pushed")
    return commit


if __name__ == "__main__":
    raise SystemExit(main())
