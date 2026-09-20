"""Commit one owner contract revision by the GER_AGENT_RUNBOOK.md "Contract edit" steps (dry run by default).

    python -B runbook_contract_commit.py --task NSC-077 --revised <json> --reason <text> [--commit]

Vincent, 2026-09-16: no re-check gate; taskcontrol validate is the only check. Steps:
- Tasks/<ID>.yaml must match HEAD; nothing may be staged; the target paths must be clean.
- id, parent, schema_version and reconciliation_key stay the same and contract_revision rises by exactly one.
- The contract is written in the file's own key order (an added superseded_by goes right after
  contract_disposition) and line endings; provenance gains a contract_followups record.
- RESOURCE_GROUPS.yaml is reconciled with apply_contract.py's helpers.
- taskcontrol validate and git diff --check must pass, or both files are restored.
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
import apply_contract as ac  # noqa: E402  (helpers only: git, sha256, serialize, resource-group reconciliation)

IDENTITY = ["-c", "user.name=No Safe Circle Contract Maintenance",
            "-c", "user.email=contract-maintenance@nosafecircle.invalid"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--task", required=True)
    parser.add_argument("--revised", required=True, type=pathlib.Path)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()
    task_id = args.task
    rel = f"Tasks/{task_id}.yaml"
    path = ac.REPO / rel

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
        "review": "none; taskcontrol validate only (Vincent, 2026-09-16)"}]
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
    if not args.commit:
        print("[DRY RUN] no file written")
        return 0

    touched = [rel] + ([groups_rel] if group_changes else [])
    if ac.git("status", "--porcelain=v1", "--", *touched).stdout.decode().strip():
        raise SystemExit("target paths already have uncommitted changes")
    if ac.git("diff", "--cached", "--name-only").stdout.decode().strip():
        raise SystemExit("the index already has staged paths; refusing to commit")

    def restore() -> None:
        path.write_bytes(original)
        groups_path.write_bytes(groups_original)

    path.write_bytes(ac.serialize(merged, b"\r\n" in original))
    if group_changes:
        groups_path.write_bytes(groups_bytes)
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
    message_path = args.revised.parent / f"COMMIT_MESSAGE.{task_id}.txt"
    message_path.write_text(
        f"TaskGraph: owner contract revision {merged['contract_revision']} for {task_id}\n\n"
        f"{args.reason}\n"
        "No re-check: taskcontrol validate is the only check (Vincent, 2026-09-16).\n"
        f"Changed fields: {', '.join(changed)}.\n\n"
        "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>\n", encoding="utf-8")
    ac.git(*IDENTITY, "commit", "-F", str(message_path))
    commit = ac.git("rev-parse", "HEAD").stdout.decode().strip()
    files = ac.git("show", "--name-only", "--format=", "HEAD").stdout.decode().split()
    print(f"[DONE] {task_id} contract commit {commit} (parent {head}; files {files}); not pushed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
