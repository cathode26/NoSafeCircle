"""Preserve conformant NSC tasks under C:/NSC/SuccessfullTasks/<TASK-ID>.

Follows Docs/AI-Pipeline/ASSISTANT_SOFTWARE_ARCHITECT.md step 10: keep the completed
Unity project and its receipt, never overwriting an existing archive. Each archive is a
standalone clone of the canonical repository checked out at the delivery record's
integrated commit, with the task's own branches kept as local branches.
"""
import json
import os
import subprocess
import sys
from datetime import date

NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW (C:\NSC\nsc-quiet-windows-guide.md)

CANONICAL = "C:/NSC/NSC/NoSafeCircle"
ARCHIVE_ROOT = "C:/NSC/SuccessfullTasks"
GITHUB = "https://github.com/cathode26/NoSafeCircle.git"
TASK_BRANCHES = {
    "NSC-003": ["milestone-2a-nsc-003-context"],
    "NSC-005": ["nsc-005-closeout"],
    "NSC-011": ["nsc-011-active-enemy-registry"],
    "NSC-028": ["codex/nsc028-cap-recovery-20260914"],
    "NSC-063": [
        "assistant/nsc063-nsc093-ne-single-cleaver-20260916",
        "codex/nsc063-melee-ne-single-cleaver-20260914",
        "codex/nsc063-delivery-evidence-20260914",
    ],
    "NSC-093": [
        "assistant/nsc063-nsc093-ne-single-cleaver-20260916",
        "codex/nsc093-current-main-review-20260914",
        "codex/nsc093-pixellab-walk-20260914",
    ],
}


def git(*args, cwd=CANONICAL):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, creationflags=NO_WINDOW)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {cwd}: {result.stderr.strip()}")
    return result.stdout.strip()


def records(task_id, prefix):
    listing = git("ls-tree", "-r", "--name-only", "main", "--", f"Pipeline/TaskGraph/evidence/{task_id}/records")
    return [path for path in listing.splitlines() if os.path.basename(path).startswith(prefix)]


def relation(branch, commit):
    if git("rev-parse", branch) == git("rev-parse", commit):
        return "its tip is the integrated commit"
    if subprocess.run(["git", "merge-base", "--is-ancestor", commit, branch], cwd=CANONICAL, creationflags=NO_WINDOW).returncode == 0:
        return "it contains the integrated commit"
    if subprocess.run(["git", "merge-base", "--is-ancestor", branch, commit], cwd=CANONICAL, creationflags=NO_WINDOW).returncode == 0:
        return "it is an ancestor of the integrated commit"
    return "a separate line of work that did not become the integrated commit"


def archive(task_id):
    target = f"{ARCHIVE_ROOT}/{task_id}"
    if os.path.exists(target):
        print(f"{task_id}: {target} already exists; left untouched")
        return

    states = subprocess.run(
        [sys.executable, "taskcontrol.py", "state", task_id], cwd=f"{CANONICAL}/Pipeline/TaskGraph",
        capture_output=True, text=True, creationflags=NO_WINDOW).stdout
    if "conformant" not in states:
        raise RuntimeError(f"{task_id} is not conformant: {states.strip()}")

    selected = [line.split(":", 1)[1].strip() for line in states.splitlines() if line.startswith("selected_record:")]
    if not selected or not selected[0].startswith("DEL-"):
        raise RuntimeError(f"{task_id}: no selected delivery record in state output: {states.strip()}")
    delivery_path = f"Pipeline/TaskGraph/evidence/{task_id}/records/{selected[0]}.json"
    delivery = json.loads(git("show", f"main:{delivery_path}"))
    integrated = delivery["delivery"]["integrated_commit"]
    candidate = delivery["delivery"].get("candidate_commit")
    approval = delivery.get("human_approval", {})
    gates = ", ".join(f"{g['gate_id']} {g['result']}" for g in delivery.get("gate_results", []))
    contract = json.loads(git("show", f"main:Tasks/{task_id}.yaml"))
    revalidations = [os.path.basename(p) for p in records(task_id, "REV-")]
    unity = git("show", f"{integrated}:ProjectSettings/ProjectVersion.txt").splitlines()[0].split(":", 1)[1].strip()
    main_head = git("rev-parse", "--short", "main")

    git("clone", "--quiet", "--no-hardlinks", "--no-checkout", CANONICAL, target, cwd=ARCHIVE_ROOT)
    git("remote", "rename", "origin", "canonical", cwd=target)
    git("remote", "add", "origin", GITHUB, cwd=target)
    branch_name = f"{task_id}-successful"
    git("checkout", "--quiet", "-b", branch_name, integrated, cwd=target)

    kept = []
    for task_branch in TASK_BRANCHES[task_id]:
        git("branch", task_branch, f"canonical/{task_branch}", cwd=target)
        tip = git("rev-parse", "--short", task_branch)
        when = git("log", "-1", "--format=%ad", "--date=short", task_branch)
        kept.append(f"`{task_branch}` at `{tip}` ({when}): {relation(task_branch, integrated)}")

    receipt = "SUCCESSFUL_TASK_RECEIPT.md"
    with open(f"{target}/.git/info/exclude", "a", encoding="utf-8") as exclude:
        exclude.write(f"\n{receipt}\n")

    lines = [
        f"# {task_id} successful task archive",
        "",
        f"- **Task:** {task_id}, {contract['title']}. Delivered against contract revision {delivery['task_contract']['revision']}; the current contract is revision {contract['contract_revision']}.",
        f"- **Task graph state when archived:** conformant, {date.today().isoformat()}.",
        f"- **Delivery record:** `{delivery_path}`.",
        f"- **Checked out:** branch `{branch_name}` at `{integrated}`, the record's integrated commit.",
        f"- **Candidate commit:** `{candidate}`.",
        f"- **Gates:** {gates}.",
        f"- **Human approval:** {approval.get('decision')} by {approval.get('approved_by') or 'n/a'}.",
    ]
    if revalidations:
        lines.append(f"- **Later revalidation records:** {', '.join(revalidations)}.")
    lines += [
        "- **Task branches kept as local branches:**",
        *[f"  - {entry}" for entry in kept],
        f"- **Source:** standalone clone of `{CANONICAL}`. The remote `canonical` holds every branch it had; main was `{main_head}` when archived. `origin` points at GitHub and was never fetched.",
        f"- **Unity:** {unity}. The Library is not included; Unity imports the project the first time it is opened.",
        "- **Archived by:** Claude, at Vincent's request. The canonical task branches and worktrees were left in place.",
        "",
    ]
    with open(f"{target}/{receipt}", "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines))

    status = git("status", "--short", cwd=target)
    print(f"{task_id}: archived at {integrated[:9]} on {branch_name}; status lines {len(status.splitlines())}")


if __name__ == "__main__":
    for task in sys.argv[1:]:
        archive(task)
