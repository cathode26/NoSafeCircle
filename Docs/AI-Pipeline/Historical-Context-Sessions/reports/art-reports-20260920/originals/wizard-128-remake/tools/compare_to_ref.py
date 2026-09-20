"""Compare a staged tree against a committed git ref, so a hand-off cannot silently revert committed work.

Usage: python compare_to_ref.py <stage_dir> <git_ref> [--repo <path>]

`verify_staged.py` only checks a tree's internal consistency: a stale-but-valid file passes it happily. The Game
Agent caught exactly that on 2026-09-17 - a staged generation record that predated its own call-log commit, which
a tree-wide copy would have reverted. This tool is the missing check.

It prints, per category, how many staged files are identical to the ref, changed, or absent from it, and fails
when a text file in the staged tree is **shorter** than the committed one, which is the signature of a revert.
"""
import hashlib
import os
import subprocess
import sys

NO_WINDOW = 0x08000000
TEXT_EXT = {".md", ".json", ".txt", ".yaml", ".yml"}


def categorise(rel):
    if "/selected/walk/" in rel:
        return "selected walk frames"
    if "/selected/standing/" in rel:
        return "selected standing frames"
    if rel.endswith("source-inventory.json"):
        return "inventory"
    if "/Raw128/" in rel:
        return "raw exports"
    return "docs and other"


def main():
    stage, ref = sys.argv[1], sys.argv[2]
    repo = r"C:\NSC\NSC\NoSafeCircle"
    if "--repo" in sys.argv:
        repo = sys.argv[sys.argv.index("--repo") + 1]

    listing = subprocess.run(["git", "-C", repo, "ls-tree", "-r", "--long", ref],
                             capture_output=True, text=True, check=True, creationflags=NO_WINDOW).stdout
    ref_files = {}
    for line in listing.splitlines():
        meta, path = line.split("\t", 1)
        _mode, _type, blob, size = meta.split()
        ref_files[path] = (blob, int(size))

    stats = {}
    shrank = []
    changed_list = []
    for root, _dirs, files in os.walk(stage):
        for f in files:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, stage).replace("\\", "/")
            cat = categorise(rel)
            s = stats.setdefault(cat, {"identical": 0, "changed": 0, "new": 0})
            if rel not in ref_files:
                s["new"] += 1
                continue
            blob, size = ref_files[rel]
            data = open(full, "rb").read()
            mine = subprocess.run(["git", "-C", repo, "hash-object", "-w", "--stdin"], input=data,
                                  capture_output=True, check=True, creationflags=NO_WINDOW).stdout.decode().strip()
            if mine == blob:
                s["identical"] += 1
            else:
                s["changed"] += 1
                changed_list.append(rel)
                if os.path.splitext(rel)[1].lower() in TEXT_EXT and len(data) < size:
                    shrank.append((rel, len(data), size))

    print(f"staged tree vs {ref} (in {repo})\n")
    for cat in sorted(stats):
        v = stats[cat]
        print(f"  {cat:28s} identical {v['identical']:4d}  changed {v['changed']:4d}  not in ref {v['new']:4d}")
    print(f"\nchanged files: {len(changed_list)}")
    for rel in changed_list[:8]:
        print("   -", rel)
    if len(changed_list) > 8:
        print(f"   ... and {len(changed_list) - 8} more")

    if shrank:
        print("\nFAIL: a staged text file is shorter than the committed one, which is what a revert looks like:")
        for rel, mine, theirs in shrank:
            print(f"   - {rel}: staged {mine} bytes vs committed {theirs}")
        sys.exit(1)
    print("\nOK: no staged text file is shorter than its committed version")


main()
