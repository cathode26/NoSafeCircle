"""Rebind stale authoritative validation policy pins to the committed contract bytes, without touching any contract (dry run by default).

    python -B policy_rebind_commit.py --task NSC-007 --task NSC-087 \
        --reason "..." --role "GER Agent" [--commit]

Why this exists: applying a decomposition rewrites Tasks/<ID>.yaml - it bumps contract_revision, repoints depends_on at
the new children and re-serializes - and Pipeline/AssistantControl/decomposition.py never rebinds the affected policy
entries, so their task_contract_sha256 still names the pre-apply bytes. downstream_resilience.py then raises "stale" for
that task, and decomposition_policy_audit_smoke_test.py fails CI. The pin is a DERIVED fact: it must equal the sha256 of
the contract already on HEAD. Binding it there needs no contract revision - the same reasoning policy_entry_commit.py
states for adding an entry - and a dispatched task's contract stays frozen, so no candidate's revise path is touched.

This is the rebind half of policy_entry_commit.py, which refuses an existing entry and points at contract_commit.py.
contract_commit.py can only rebind as a side effect of --revised, i.e. of a real contract revision; bumping a contract to
correct a hash it does not mention would be a sham revision, and on a task holding a candidate it is a hazard.

Rules: the policy file must match HEAD, nothing may be staged, every named task must already HAVE an entry whose pin is
actually stale, ONLY task_contract_sha256 may change and only for the named tasks - platforms, filters and authority are
preserved byte for byte - and taskcontrol validate must pass or the file is restored.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import pathlib
import subprocess
import sys

# Same shim as policy_entry_commit.py: prefer the maintained helper location.
for _helpers in (pathlib.Path(__file__).resolve().parents[1] / "ger",
                 pathlib.Path(r"C:\NSC\tools\ger"), pathlib.Path(r"C:\nscrev\ger-tools")):
    if os.path.isdir(_helpers):
        sys.path.insert(0, str(_helpers))
        break
else:
    raise SystemExit(
        "cannot find the GER helper tools at C:\\NSC\\tools\\ger or C:\\nscrev\\ger-tools; "
        "refusing to run, because the stale main_write.py next to this script would "
        "otherwise be imported instead."
    )
import apply_contract as ac  # noqa: E402
import main_write  # noqa: E402

IDENTITY = ["-c", "user.name=No Safe Circle Contract Maintenance",
            "-c", "user.email=contract-maintenance@nosafecircle.invalid"]
POLICY_REL = "Pipeline/TaskReviewAgent/authoritative_validation_policy.json"
PIN = "task_contract_sha256"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--task", action="append", required=True,
                        help="repeatable; all named tasks are rebound in ONE commit, because the audit "
                             "raises on the first stale task rather than collecting, so fixing them one "
                             "at a time turns one red CI run into one per task.")
    parser.add_argument("--reason", required=True)
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--role", default=None,
                        help="the role writing to main, e.g. 'GER Agent'. Falls back to NSC_ROLE.")
    args = parser.parse_args()

    tasks = list(dict.fromkeys(args.task))
    head = ac.git("rev-parse", "HEAD").stdout.decode().strip()
    if ac.git("diff", "--cached", "--name-only").stdout.decode().strip():
        raise SystemExit("the index already has staged paths; refusing")

    policy_path = ac.REPO / POLICY_REL
    original = policy_path.read_bytes()
    if original.replace(b"\r\n", b"\n") != ac.git("show", f"HEAD:{POLICY_REL}").stdout.replace(b"\r\n", b"\n"):
        raise SystemExit(f"{POLICY_REL} differs from HEAD; refusing")
    data = json.loads(original)
    before = copy.deepcopy(data)

    print(f"[PLAN] HEAD {head}")
    rebound = {}
    for task in tasks:
        entry = data["tasks"].get(task)
        if entry is None:
            raise SystemExit(f"{task} has no entry; use policy_entry_commit.py to add one")
        blob = ac.git("show", f"HEAD:Tasks/{task}.yaml").stdout
        if not blob:
            raise SystemExit(f"Tasks/{task}.yaml does not exist on HEAD")
        blob_sha = ac.sha256(blob)
        old = entry.get(PIN)
        if old == blob_sha:
            raise SystemExit(f"{task} is already bound to {blob_sha}; nothing to rebind")
        contract = json.loads(blob)
        entry[PIN] = blob_sha
        rebound[task] = (old, blob_sha, contract.get("contract_revision"))
        print(f"[PLAN] {task} (revision {contract['contract_revision']}) {old} -> {blob_sha}")

    # Only the pin, and only for the named tasks. Everything else must be untouched.
    changed = [t for t in before["tasks"] if before["tasks"][t] != data["tasks"][t]]
    if sorted(changed) != sorted(tasks):
        raise SystemExit(f"refusing: entries changed {sorted(changed)} but only {sorted(tasks)} were named")
    for task in tasks:
        a, b = dict(before["tasks"][task]), dict(data["tasks"][task])
        a.pop(PIN, None)
        b.pop(PIN, None)
        if a != b:
            raise SystemExit(f"refusing: {task} changed a field other than {PIN}")
    if sorted(before.keys()) != sorted(data.keys()) or before.get("schema_version") != data.get("schema_version"):
        raise SystemExit("refusing: a top-level policy key changed")
    if before.get("decomposition_child_templates") != data.get("decomposition_child_templates"):
        raise SystemExit("refusing: decomposition_child_templates changed")
    print(f"[PLAN] exactly {len(tasks)} entries change, {PIN} only; "
          f"{len(data['tasks']) - len(tasks)} entries untouched")

    new_bytes = ac.serialize(data, b"\r\n" in original)
    if not args.commit:
        print("[DRY RUN] no file written")
        return 0

    if ac.git("status", "--porcelain=v1", "--", POLICY_REL).stdout.decode().strip():
        raise SystemExit("the policy file already has uncommitted changes")
    if ac.git("rev-parse", "HEAD").stdout.decode().strip() != head:
        raise SystemExit("HEAD moved since planning; rerun")
    journal = main_write.default_journal(ac.REPO)
    label = "validation policy rebind (no contract change): " + ", ".join(tasks)
    with main_write.transaction(label, head, role=args.role, journal=journal, repo=ac.REPO,
                                touched=[POLICY_REL], expected_files={POLICY_REL: original}):
        policy_path.write_bytes(new_bytes)
        validate = main_write.run_process(
            [sys.executable, "-B", "Pipeline/TaskGraph/taskcontrol.py", "validate"], cwd=str(ac.REPO),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"})
        if validate.returncode != 0 or "PASS" not in validate.stdout:
            policy_path.write_bytes(original)
            raise SystemExit(f"taskcontrol validate failed; restored:\n{(validate.stdout + validate.stderr).strip()[-800:]}")
        ac.git("add", "--", POLICY_REL)
        staged = [line for line in ac.git("diff", "--cached", "--name-only").stdout.decode().splitlines() if line]
        if staged != [POLICY_REL]:
            ac.git("reset", "-q", "--", POLICY_REL)
            policy_path.write_bytes(original)
            raise SystemExit(f"unexpected staged paths {staged}; unstaged and restored")
        lines = "".join(f"{t}: {o} -> {n} (contract revision {r}, unchanged)\n"
                        for t, (o, n, r) in rebound.items())
        message = main_write._git_dir(ac.REPO) / "COMMIT_MESSAGE.policy-rebind.txt"
        message.write_text(
            f"TaskReviewAgent: rebind {len(tasks)} stale validation policy pins to the committed contract bytes\n\n"
            f"{args.reason}\n\n{lines}\n"
            "No contract changed. Only task_contract_sha256 moved, and only for the tasks listed above;\n"
            "platforms, filters and authority are preserved for every entry.\n\n"
            "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>\n", encoding="utf-8")
        ac.git(*IDENTITY, "commit", "-F", str(message))
        commit = ac.git("rev-parse", "HEAD").stdout.decode().strip()
        print(f"[DONE] rebound {len(tasks)} entries, committed {commit} (parent {head}); not pushed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
