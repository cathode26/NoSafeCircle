"""Commit brand-new task contracts (contract_revision 1) in one commit (dry run by default).

    python -B new_task_commit.py --new NSC-095=<json> [--new NSC-096=<json> ...] --template NSC-093 --reason <text>
        [--policy-filters-file <json {"NSC-095": {"EditMode": "..."}}>] [--review <text>] [--commit]

GER Agent tool (2026-09-17). The same rules as runbook_contract_commit.py, adapted to new tasks:
- Every Tasks/ file, WORK_ID_MAP.json, RESOURCE_GROUPS.yaml and the validation policy must match HEAD
  (line endings aside); nothing may be staged.
- New IDs must be absent and contiguous from the highest existing NSC number (the decomposition allocator
  uses max + 1). Each draft's id matches, contract_revision is 1, its top-level keys equal the template
  task's keys in order, schema_version equals the template's, its reconciliation_key is unused, its parent
  and depends_on name existing or new tasks, and provenance has no contract_followups.
- WORK_ID_MAP.json gains one id_map entry per task, appended in ID order (as apply_graph_delta does).
- RESOURCE_GROUPS.yaml is reconciled with apply_contract.py's helpers.
- --policy-filters-file creates a validation policy entry per named task, bound to the sha256 of the
  contract's LF bytes; the staged blob must hash to that value.
- taskcontrol validate and git diff --check must pass, or every file is restored.
- Exactly those paths are staged and committed as No Safe Circle Contract Maintenance (.invalid), with
  MAIN-WRITE START/END journal markers. Never pushes.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
# Installed G15b helpers win. Prefer the maintained location: C:\nscrev\ger-tools is
# only a junction to it, sits at depth 2 inside the tree the cleanup walks, and if it
# is ever removed nothing else puts these helpers on sys.path (PYTHONPATH is unset and
# no .pth adds them). The junction is kept as a fallback in case the move is reversed.
for _helpers in (r"C:\NSC\tools\ger", r"C:\nscrev\ger-tools"):
    if os.path.isdir(_helpers):
        sys.path.insert(0, _helpers)
        break
else:  # fail loudly rather than silently importing the stale main_write.py alongside
    raise SystemExit(
        "cannot find the GER helper tools at C:\\NSC\\tools\\ger or C:\\nscrev\\ger-tools; "
        "refusing to run, because the stale main_write.py next to this script would "
        "otherwise be imported instead."
    )
import apply_contract as ac  # noqa: E402  (helpers only: git, sha256, serialize, resource-group reconciliation)
import main_write  # noqa: E402  (installed G15b: the journal functions take journal=)

IDENTITY = ["-c", "user.name=No Safe Circle Contract Maintenance",
            "-c", "user.email=contract-maintenance@nosafecircle.invalid"]
ID_RE = re.compile(r"NSC-(\d{3})")
GROUPS_REL = "Pipeline/TaskGraph/RESOURCE_GROUPS.yaml"
IDMAP_REL = "Pipeline/TaskGraph/WORK_ID_MAP.json"
POLICY_REL = "Pipeline/TaskReviewAgent/authoritative_validation_policy.json"


def lf(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--new", action="append", required=True, metavar="ID=JSON")
    parser.add_argument("--template", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--policy-filters-file", type=pathlib.Path)
    parser.add_argument("--review", default="post-commit contract closure review (tiered rule, 2026-09-17)")
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()

    head = ac.git("rev-parse", "HEAD").stdout.decode().strip()
    if ac.git("diff", "--cached", "--name-only").stdout.decode().strip():
        raise SystemExit("the index already has staged paths; refusing")
    committed = {}
    for rel in ac.git("ls-tree", "--name-only", "HEAD", "Tasks/").stdout.decode().split():
        if ID_RE.fullmatch(pathlib.PurePosixPath(rel).stem):
            working = (ac.REPO / rel).read_bytes()
            if lf(working) != lf(ac.git("show", f"HEAD:{rel}").stdout):
                raise SystemExit(f"{rel} differs from HEAD; refusing")
            committed[pathlib.PurePosixPath(rel).stem] = json.loads(working)
    template = committed.get(args.template)
    if template is None:
        raise SystemExit(f"template {args.template} not found")
    template_crlf = b"\r\n" in (ac.REPO / f"Tasks/{args.template}.yaml").read_bytes()

    drafts: dict[str, dict] = {}
    for spec in args.new:
        task_id, _, source = spec.partition("=")
        if not ID_RE.fullmatch(task_id) or not source:
            raise SystemExit(f"bad --new {spec!r}; use NSC-###=<json path>")
        if task_id in drafts or task_id in committed or (ac.REPO / f"Tasks/{task_id}.yaml").exists():
            raise SystemExit(f"{task_id} already exists or is repeated")
        drafts[task_id] = json.loads(pathlib.Path(source).read_bytes())
    top = max(int(ID_RE.fullmatch(task_id).group(1)) for task_id in committed)
    expected = [f"NSC-{top + offset:03d}" for offset in range(1, len(drafts) + 1)]
    if sorted(drafts) != expected:
        raise SystemExit(f"new IDs must be {expected} (highest existing is NSC-{top:03d}); got {sorted(drafts)}")

    idmap_bytes_head = ac.git("show", f"HEAD:{IDMAP_REL}").stdout
    idmap_original = (ac.REPO / IDMAP_REL).read_bytes()
    if lf(idmap_original) != lf(idmap_bytes_head):
        raise SystemExit(f"{IDMAP_REL} differs from HEAD; refusing")
    idmap_crlf = b"\r\n" in idmap_original
    idmap = json.loads(idmap_original)
    if ac.serialize(idmap, idmap_crlf) != idmap_original:
        raise SystemExit(f"{IDMAP_REL} is not in json.dumps(indent=2) form; refusing to reserialize it")
    used_keys = {task["reconciliation_key"] for task in committed.values()} | set(idmap["id_map"])
    known_ids = set(committed) | set(drafts)
    for task_id in expected:
        draft = drafts[task_id]
        if draft.get("id") != task_id:
            raise SystemExit(f"{task_id}: draft id is {draft.get('id')!r}")
        if draft.get("contract_revision") != 1:
            raise SystemExit(f"{task_id}: contract_revision must be 1")
        if list(draft) != list(template):
            raise SystemExit(f"{task_id}: top-level keys differ from {args.template}: missing "
                             f"{sorted(set(template) - set(draft))}, extra {sorted(set(draft) - set(template))}, "
                             f"or a different order")
        if draft.get("schema_version") != template.get("schema_version"):
            raise SystemExit(f"{task_id}: schema_version differs from {args.template}")
        key = draft.get("reconciliation_key")
        if not isinstance(key, str) or not key.strip() or key in used_keys:
            raise SystemExit(f"{task_id}: reconciliation_key {key!r} is blank or already used")
        used_keys.add(key)
        if draft.get("parent") not in known_ids:
            raise SystemExit(f"{task_id}: parent {draft.get('parent')!r} is not a known task")
        unknown = [dep for dep in draft.get("depends_on") or [] if dep not in known_ids]
        if unknown:
            raise SystemExit(f"{task_id}: unknown depends_on {unknown}")
        if (draft.get("provenance") or {}).get("contract_followups"):
            raise SystemExit(f"{task_id}: a new contract carries no contract_followups")
        idmap["id_map"][key] = task_id
        print(f"[PLAN] new {task_id} ({key}): {draft.get('title')}; parent {draft['parent']}; "
              f"depends_on {draft.get('depends_on')}; {len(draft.get('exclusive_resources') or [])} resources")
    idmap_bytes = ac.serialize(idmap, idmap_crlf)

    groups_path = ac.REPO / GROUPS_REL
    groups_original = groups_path.read_bytes()
    if lf(groups_original) != lf(ac.git("show", f"HEAD:{GROUPS_REL}").stdout):
        raise SystemExit(f"{GROUPS_REL} differs from HEAD; refusing")
    groups_crlf = b"\r\n" in groups_original
    groups_data = json.loads(groups_original)
    groups_canonical = ac.serialize(groups_data, groups_crlf) == groups_original
    all_tasks = [committed[task_id] for task_id in sorted(committed)] + [drafts[task_id] for task_id in expected]
    group_changes = ac.reconcile_resource_groups(groups_data["resource_groups"], all_tasks)
    for change in group_changes:
        after = change["after"]
        entry = {"reconciliation_keys": after["reconciliation_keys"], "resource_key": after["resource_key"],
                 "work_ids": after["work_ids"]}
        if change["change_type"] == "updated":
            index = next(i for i, group in enumerate(groups_data["resource_groups"])
                         if group["resource_key"] == after["resource_key"])
            groups_data["resource_groups"][index] = entry
        else:
            groups_data["resource_groups"].append(entry)
        print(f"[PLAN] resource group {change['change_type']}: {after['resource_key']} -> {after['work_ids']}")
    groups_bytes = None
    if group_changes:
        groups_bytes = (ac.serialize(groups_data, groups_crlf) if groups_canonical
                        else ac.append_created_groups(groups_original, groups_data, group_changes, groups_crlf))

    policy_path = ac.REPO / POLICY_REL
    policy_original = policy_path.read_bytes()
    if lf(policy_original) != lf(ac.git("show", f"HEAD:{POLICY_REL}").stdout):
        raise SystemExit(f"{POLICY_REL} differs from HEAD; refusing")
    policy_bytes = None
    bound: dict[str, str] = {}
    if args.policy_filters_file:
        filters = json.loads(args.policy_filters_file.read_bytes().decode("utf-8"))
        policy_data = json.loads(policy_original)
        for task_id, platforms in filters.items():
            if task_id not in drafts:
                raise SystemExit(f"policy filters name {task_id}, which is not a new task here")
            if (not isinstance(platforms, dict) or not platforms
                    or any(p not in ("EditMode", "PlayMode") or not isinstance(v, str) or not v.strip()
                           for p, v in platforms.items())):
                raise SystemExit(f"policy filters for {task_id} must map EditMode/PlayMode to non-empty strings")
            if task_id in policy_data["tasks"]:
                raise SystemExit(f"the policy already has an entry for {task_id}")
            bound[task_id] = ac.sha256(ac.serialize(drafts[task_id], False))
            policy_data["tasks"][task_id] = {"task_contract_sha256": bound[task_id],
                                             "required_test_platforms": list(platforms),
                                             "test_filters": dict(platforms),
                                             "authority": "committed_task_specific_authoritative_validation_policy"}
            print(f"[PLAN] validation policy created for {task_id}: {bound[task_id][:16]}; filters {platforms}")
        policy_bytes = ac.serialize(policy_data, b"\r\n" in policy_original)

    if not args.commit:
        print("[DRY RUN] no file written")
        return 0

    new_rels = [f"Tasks/{task_id}.yaml" for task_id in expected]
    touched = new_rels + [IDMAP_REL] + ([GROUPS_REL] if groups_bytes else []) + ([POLICY_REL] if policy_bytes else [])
    if ac.git("status", "--porcelain=v1", "--", *touched).stdout.decode().strip():
        raise SystemExit("target paths already have uncommitted changes")

    def restore() -> None:
        for rel in new_rels:
            (ac.REPO / rel).unlink(missing_ok=True)
        (ac.REPO / IDMAP_REL).write_bytes(idmap_original)
        groups_path.write_bytes(groups_original)
        policy_path.write_bytes(policy_original)

    if ac.git("rev-parse", "HEAD").stdout.decode().strip() != head:
        raise SystemExit("HEAD moved since planning; rerun")
    operation = f"new task contracts {', '.join(expected)}"
    journal = main_write.default_journal(ac.REPO)
    main_write.start(operation, head, journal=journal)
    try:
        for task_id in expected:
            (ac.REPO / f"Tasks/{task_id}.yaml").write_bytes(ac.serialize(drafts[task_id], template_crlf))
        (ac.REPO / IDMAP_REL).write_bytes(idmap_bytes)
        if groups_bytes:
            groups_path.write_bytes(groups_bytes)
        if policy_bytes:
            policy_path.write_bytes(policy_bytes)
        validate = subprocess.run([sys.executable, "-B", "Pipeline/TaskGraph/taskcontrol.py", "validate"],
                                  cwd=str(ac.REPO), capture_output=True, creationflags=0x08000000, text=True, encoding="utf-8", errors="replace",
                                  env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"})
        print(validate.stdout.strip()[-300:])
        if validate.returncode != 0 or "PASS" not in validate.stdout:
            restore()
            raise SystemExit(f"taskcontrol validate failed; restored:\n{(validate.stdout + validate.stderr).strip()[-1500:]}")
        if ac.git("diff", "--check", "--", *touched, check=False).returncode != 0:
            restore()
            raise SystemExit("git diff --check failed; restored")
        ac.git("add", "--", *touched)
        staged = sorted(line for line in ac.git("diff", "--cached", "--name-only").stdout.decode().splitlines() if line)
        if staged != sorted(touched):
            ac.git("reset", "-q", "--", *touched)
            restore()
            raise SystemExit(f"unexpected staged paths {staged}; unstaged and restored")
        for task_id, blob_sha in bound.items():
            if ac.sha256(ac.git("show", f":Tasks/{task_id}.yaml").stdout) != blob_sha:
                ac.git("reset", "-q", "--", *touched)
                restore()
                raise SystemExit(f"staged {task_id} blob hash differs from its policy hash; unstaged and restored")
        message_path = pathlib.Path(__file__).resolve().parent / f"COMMIT_MESSAGE.{'_'.join(expected)}.txt"
        message_path.write_text(
            f"TaskGraph: add {' and '.join(expected)}\n\n"
            + "".join(f"{task_id} ({drafts[task_id]['reconciliation_key']}): {drafts[task_id]['title']}.\n"
                      for task_id in expected)
            + f"\n{args.reason}\n"
            f"Review: {args.review}.\n"
            + "".join(f"Validation policy entry for {task_id} bound to contract sha256 {sha}.\n"
                      for task_id, sha in bound.items())
            + "\nCo-Authored-By: Claude Opus 5 <noreply@anthropic.com>\n", encoding="utf-8")
        ac.git(*IDENTITY, "commit", "-F", str(message_path))
        commit = ac.git("rev-parse", "HEAD").stdout.decode().strip()
    except BaseException as error:
        now = ac.git("rev-parse", "HEAD").stdout.decode().strip()
        if now == head:
            ac.git("reset", "-q", "--", *touched, check=False)
            restore()
        main_write.end(now, f"aborted, nothing committed ({error})" if now == head else f"UNEXPECTED: HEAD moved during the write ({error})",
                       journal=journal)
        raise
    files = ac.git("show", "--name-only", "--format=", "HEAD").stdout.decode().split()
    print(f"[DONE] {', '.join(expected)} committed {commit} (parent {head}; files {files}); not pushed")
    main_write.end(commit, f"{', '.join(expected)} rev 1; taskcontrol validate PASS; not pushed", journal=journal)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
