"""Archive every merged NSC task into C:/NSC/SuccessfullTasks, one task at a time.

Wraps the existing archive script (p35-archive-successful/archive_successful_tasks.py) and
derives each task's branches from the branch names instead of its hardcoded table. Only local
branches whose commits are all in main (ancestry or patch-equivalent) are kept in the archive.

Usage: archive script with no arguments archives every candidate task; pass task ids to limit it.
"""
import importlib.util
import re
import subprocess
import sys

NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW (C:\NSC\nsc-quiet-windows-guide.md)

CANONICAL = "C:/NSC/NSC/NoSafeCircle"
ARCHIVER = "C:/nscrev/reports/handoffs/p35-archive-successful/archive_successful_tasks.py"

spec = importlib.util.spec_from_file_location("archiver", ARCHIVER)
archiver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archiver)


def git(*args):
    return subprocess.run(["git", "-C", CANONICAL, *args], capture_output=True, text=True, creationflags=NO_WINDOW).stdout.splitlines()


local_branches = [b for b in git("for-each-ref", "--format=%(refname:short)", "refs/heads") if b != "main"]
merged = {b.strip() for b in git("branch", "--merged", "main", "--format=%(refname:short)")}


def fully_in_main(branch):
    if branch in merged:
        return True
    return not any(line.startswith("+") for line in git("cherry", "main", branch))


def branches_for(task_id):
    number = task_id.split("-")[1]
    pattern = re.compile(rf"nsc[-_]?{number}(\D|$)", re.IGNORECASE)
    return sorted(b for b in local_branches if pattern.search(b) and fully_in_main(b))


tasks = sys.argv[1:]
if not tasks:
    found = set()
    for branch in local_branches:
        match = re.search(r"nsc[-_]?(\d{3})", branch, re.IGNORECASE)
        if match and fully_in_main(branch):
            found.add(f"NSC-{match.group(1)}")
    tasks = sorted(found)

print(f"tasks to attempt: {len(tasks)}")
archived, skipped, failed = [], [], []
for task_id in tasks:
    kept = branches_for(task_id)
    archiver.TASK_BRANCHES[task_id] = kept
    try:
        before = archiver.os.path.exists(f"{archiver.ARCHIVE_ROOT}/{task_id}")
        archiver.archive(task_id)
        (skipped if before else archived).append(task_id)
    except Exception as error:  # a task without a conformant delivery record, and anything else
        failed.append((task_id, str(error).splitlines()[0][:160]))
        print(f"{task_id}: SKIPPED - {str(error).splitlines()[0][:160]}")

print(f"\narchived now: {len(archived)} -> {', '.join(archived) or 'none'}")
print(f"already there: {len(skipped)}")
print(f"not archived: {len(failed)}")
for task_id, reason in failed:
    print(f"  {task_id}: {reason}")
