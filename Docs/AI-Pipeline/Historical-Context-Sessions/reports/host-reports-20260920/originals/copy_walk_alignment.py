"""Copy only the walk-alignment changes into the clone: 132 walk PNGs, the inventory, the record.

Path-limited by design. The Art Director's staged-v2 tree also contains 316 files that are
byte-identical to what is committed, and one earlier version of it carried a STALE generation
record that would have reverted the call-log itemisation. So this copies only files that differ,
and refuses if the shape is not exactly what was verified.
"""
import filecmp
import os
import shutil
import sys

STAGED = r'C:\nscrev\reports\art-director\wizard-128-remake\staged-v2'
CLONE = r'C:\nscrev\cj-nsc095'

changed = []
for root, _dirs, files in os.walk(STAGED):
    for name in files:
        src = os.path.join(root, name)
        rel = os.path.relpath(src, STAGED)
        dst = os.path.join(CLONE, rel)
        if not os.path.exists(dst):
            changed.append((rel, 'new'))
            continue
        if not filecmp.cmp(src, dst, shallow=False):
            changed.append((rel, 'modified'))


def bucket(rel):
    rel = rel.replace('\\', '/')
    if rel.endswith('source-inventory.json'):
        return 'inventory'
    if '/Raw128/' in rel:
        return 'raw export'
    if '/walk/' in rel or '_walk' in rel:
        return 'walk frame'
    return 'other (standing/doc)'


counts = {}
for rel, _kind in changed:
    counts[bucket(rel)] = counts.get(bucket(rel), 0) + 1

print('files differing from the clone: %d' % len(changed))
for kind in sorted(counts):
    print('   %-22s %d' % (kind, counts[kind]))

expected = {'walk frame': 132, 'inventory': 1, 'other (standing/doc)': 1}
if counts != expected:
    print()
    print('ABORT: expected exactly %s' % expected)
    print('Nothing was copied. Re-verify with compare_v2_to_branch.py before retrying.')
    sys.exit(1)

for rel, _kind in changed:
    src = os.path.join(STAGED, rel)
    dst = os.path.join(CLONE, rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)

print()
print('copied %d files into %s' % (len(changed), CLONE))
