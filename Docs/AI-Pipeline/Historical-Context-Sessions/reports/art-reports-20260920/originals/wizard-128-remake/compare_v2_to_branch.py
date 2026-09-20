"""Compare the staged-v2 tree against what is committed on nsc095-wizard-128-art.

Independent check of the Art Director's claim that only the 192 walk PNGs and
source-inventory.json differ, and that the 32 standing frames, the 224 raw exports and the
generation record are byte-identical. Compares git blob ids: the committed ids come from
ls-tree, the local ones from hash-object, so nothing has to stream blob contents.
"""
import os
import subprocess
import sys

GIT_DIR = r'C:\NSC\NSC\NoSafeCircle\.git'
COMMIT = 'c634c6496'
STAGED = r'C:\nscrev\reports\art-director\wizard-128-remake\staged-v2'
NO_WINDOW = 0x08000000


def git(args, cwd=None):
    return subprocess.run(['git', '--git-dir', GIT_DIR] + args, cwd=cwd,
                          capture_output=True, check=True,
                          creationflags=NO_WINDOW).stdout


committed = {}
for line in git(['ls-tree', '-r', COMMIT]).decode('utf-8', 'replace').splitlines():
    meta, path = line.split('\t', 1)
    committed[path] = meta.split()[2]

staged_paths = []
for root, _dirs, files in os.walk(STAGED):
    for name in files:
        rel = os.path.relpath(os.path.join(root, name), STAGED).replace('\\', '/')
        staged_paths.append(rel)
staged_paths.sort()

# hash-object in chunks: one argv per batch keeps us well under the Windows limit.
local = {}
CHUNK = 60
for start in range(0, len(staged_paths), CHUNK):
    batch = staged_paths[start:start + CHUNK]
    out = git(['hash-object'] + [p.replace('/', os.sep) for p in batch], cwd=STAGED)
    oids = out.decode().split()
    if len(oids) != len(batch):
        print('ABORT: hash-object returned %d ids for %d paths' % (len(oids), len(batch)))
        sys.exit(1)
    local.update(zip(batch, oids))

missing = [p for p in staged_paths if p not in committed]
differ = [p for p in staged_paths if p in committed and local[p] != committed[p]]
same = [p for p in staged_paths if p in committed and local[p] == committed[p]]


def bucket(path):
    if path.endswith('source-inventory.json'):
        return 'inventory'
    if '/Raw128/' in path:
        return 'raw export'
    if '/walk/' in path or '_walk' in path:
        return 'walk frame'
    return 'other (standing/doc)'


def tally(paths):
    counts = {}
    for path in paths:
        counts[bucket(path)] = counts.get(bucket(path), 0) + 1
    return counts


print('staged files          : %d' % len(staged_paths))
print('not present in commit : %d %s' % (len(missing), missing[:3]))
print('byte-identical        : %d' % len(same))
print('differ                : %d' % len(differ))
for kind, count in sorted(tally(differ).items()):
    print('   differ   %-20s %d' % (kind, count))
for kind, count in sorted(tally(same).items()):
    print('   same     %-20s %d' % (kind, count))

counts = tally(differ)
# Expectation as of 2026-09-17, after the Art Director corrected the generation record:
# 132 of the 192 walk frames changed (60 needed no shift), the inventory changed, and the
# generation record changed deliberately. The 32 standing frames and 224 raw exports must not.
ok = (counts.get('walk frame', 0) == 132
      and counts.get('inventory', 0) == 1
      and counts.get('raw export', 0) == 0
      and counts.get('other (standing/doc)', 0) == 1
      and not missing)
print()
print('EXPECTED: 132 walk frames, the inventory and the generation record, nothing else' if ok
      else 'UNEXPECTED SHAPE - re-read the counts above before committing')
sys.exit(0 if ok else 1)
