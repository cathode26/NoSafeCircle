"""Add a missing authoritative validation policy entry for a task, without touching the contract (dry run by default).

    python -B policy_entry_commit.py --task NSC-007 \
        --editmode NoSafeCircle.DoorPrototype.Tests.Editor.FireballCommittedSceneConformanceTests \
        --playmode NoSafeCircle.DoorPrototype.Tests.FireballPlayModeTests \
        --reason "..." [--commit]

Why this exists: a task whose gates name Unity fixtures but has no policy entry cannot be authoritatively validated - the
candidate stays retained exactly as with a stale entry (Pipeline/AssistantControl/README.md). Adding the entry binds it to
the contract blob already on HEAD, so no contract revision is needed and a dispatched task's contract stays frozen.

Rules: the policy file must match HEAD, nothing may be staged, the task must exist with no entry yet (use
contract_commit.py to rebind an existing one), and taskcontrol validate must pass or the file is restored.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys

# Prefer the maintained location: C:\nscrev\ger-tools is only a junction to it, sits at
# depth 2 inside the tree the cleanup walks, and if it is ever removed nothing else puts
# these helpers on sys.path (PYTHONPATH is unset and no .pth adds them). The junction is
# kept as a fallback in case the move is reversed.
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
import apply_contract as ac  # noqa: E402
import main_write  # noqa: E402

IDENTITY = ["-c", "user.name=No Safe Circle Contract Maintenance",
            "-c", "user.email=contract-maintenance@nosafecircle.invalid"]
POLICY_REL = "Pipeline/TaskReviewAgent/authoritative_validation_policy.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--task", required=True)
    parser.add_argument("--editmode")
    parser.add_argument("--playmode")
    parser.add_argument("--reason", required=True)
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()
    if not args.editmode and not args.playmode:
        raise SystemExit("give --editmode and/or --playmode filters")

    head = ac.git("rev-parse", "HEAD").stdout.decode().strip()
    if ac.git("diff", "--cached", "--name-only").stdout.decode().strip():
        raise SystemExit("the index already has staged paths; refusing")
    contract_rel = f"Tasks/{args.task}.yaml"
    blob = ac.git("show", f"HEAD:{contract_rel}").stdout
    contract = json.loads(blob)
    blob_sha = ac.sha256(blob)

    policy_path = ac.REPO / POLICY_REL
    original = policy_path.read_bytes()
    if original.replace(b"\r\n", b"\n") != ac.git("show", f"HEAD:{POLICY_REL}").stdout.replace(b"\r\n", b"\n"):
        raise SystemExit(f"{POLICY_REL} differs from HEAD; refusing")
    data = json.loads(original)
    if args.task in data["tasks"]:
        raise SystemExit(f"{args.task} already has an entry; use contract_commit.py to rebind it")

    platforms, filters = [], {}
    for name, value in (("EditMode", args.editmode), ("PlayMode", args.playmode)):
        if value:
            platforms.append(name)
            filters[name] = value
    data["tasks"][args.task] = {"task_contract_sha256": blob_sha,
                                "required_test_platforms": platforms,
                                "test_filters": filters,
                                "authority": "committed_task_specific_authoritative_validation_policy"}
    new_bytes = ac.serialize(data, b"\r\n" in original)
    print(f"[PLAN] {args.task} (revision {contract['contract_revision']}) at HEAD {head}")
    print(f"[PLAN] policy entry created, bound to contract sha256 {blob_sha}; filters {filters}")
    if not args.commit:
        print("[DRY RUN] no file written")
        return 0

    if ac.git("status", "--porcelain=v1", "--", POLICY_REL).stdout.decode().strip():
        raise SystemExit("the policy file already has uncommitted changes")
    if ac.git("rev-parse", "HEAD").stdout.decode().strip() != head:
        raise SystemExit("HEAD moved since planning; rerun")
    journal = main_write.default_journal(ac.REPO)
    main_write.start(f"{args.task} validation policy entry (no contract change)", head, journal=journal)
    try:
        policy_path.write_bytes(new_bytes)
        validate = subprocess.run([sys.executable, "-B", "Pipeline/TaskGraph/taskcontrol.py", "validate"], cwd=str(ac.REPO),
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
        message = pathlib.Path(__file__).resolve().parent / f"COMMIT_MESSAGE.policy.{args.task}.txt"
        message.write_text(
            f"TaskReviewAgent: add the validation policy entry for {args.task}\n\n{args.reason}\n"
            f"Bound to the committed contract sha256 {blob_sha} (revision {contract['contract_revision']}); "
            f"filters {json.dumps(filters)}.\nNo contract change.\n\n"
            "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>\n", encoding="utf-8")
        ac.git(*IDENTITY, "commit", "-F", str(message))
        commit = ac.git("rev-parse", "HEAD").stdout.decode().strip()
    except BaseException as error:
        now = ac.git("rev-parse", "HEAD").stdout.decode().strip()
        if now == head:
            ac.git("reset", "-q", "--", POLICY_REL, check=False)
            policy_path.write_bytes(original)
        main_write.end(now, f"aborted, nothing committed ({error})", journal=journal)
        raise
    print(f"[DONE] {args.task} policy entry committed {commit} (parent {head}); not pushed")
    main_write.end(commit, f"{args.task} validation policy entry; taskcontrol validate PASS; not pushed", journal=journal)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
