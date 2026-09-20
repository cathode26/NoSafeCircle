"""GUID reference map for the enemy art, text half.

For every PNG under Art/Enemies, resolve its .meta GUID and find every YAML asset that cites it,
then follow clips into animator controllers. The committed scene is BINARY, so scene references
cannot be seen this way at all - that half needs a Unity probe, and this script says so rather
than reporting an absence it cannot measure.
"""
import collections
import re
import subprocess

GIT_DIR = r'C:\NSC\NSC\NoSafeCircle\.git'
REV = 'main'
NO_WINDOW = 0x08000000


def git(*args):
    return subprocess.run(['git', '--git-dir', GIT_DIR] + list(args),
                          capture_output=True, creationflags=NO_WINDOW).stdout


tree = git('ls-tree', '-r', '--name-only', REV).decode('utf-8', 'replace').splitlines()

art = [p for p in tree if p.startswith('Assets/NoSafeCircle/DoorPrototype/Art/Enemies/')
       and p.endswith('.png')]
print('enemy PNGs at %s: %d' % (REV, len(art)))

# guid -> art path
guid_of = {}
for png in art:
    meta = git('cat-file', '-p', '%s:%s.meta' % (REV, png)).decode('utf-8', 'replace')
    found = re.search(r'guid:\s*([0-9a-f]{32})', meta)
    if found:
        guid_of[found.group(1)] = png

print('resolved GUIDs: %d' % len(guid_of))

# Scan every YAML-ish asset once, recording which enemy GUIDs it cites.
SCANNABLE = ('.anim', '.controller', '.prefab', '.asset', '.unity', '.mat', '.overrideController')
cited_by = collections.defaultdict(list)
binary_scenes = []
for path in tree:
    if not path.endswith(SCANNABLE):
        continue
    blob = git('cat-file', '-p', '%s:%s' % (REV, path))
    head = blob[:200]
    if b'\x00' in head:
        binary_scenes.append(path)
        continue
    text = blob.decode('utf-8', 'replace')
    for guid in guid_of:
        if guid in text:
            cited_by[guid].append(path)

referenced = {g: v for g, v in cited_by.items() if v}
orphans = [guid_of[g] for g in guid_of if g not in referenced]

print()
print('referenced by at least one YAML asset : %d' % len(referenced))
print('cited nowhere in YAML                  : %d' % len(orphans))
print()
print('BINARY assets that could NOT be scanned (GUIDs are not ASCII in these):')
for path in binary_scenes:
    print('   %s' % path)
print('   -> scene/prefab references in these are UNKNOWN from text alone; a Unity probe is required')

kinds = collections.Counter()
for guid, paths in referenced.items():
    for p in paths:
        kinds[p.rsplit('.', 1)[-1]] += 1
print()
print('citation kinds: %s' % dict(kinds))

print()
print('orphans by family (cited in no YAML asset):')
family = collections.Counter()
for path in orphans:
    name = path.rsplit('/', 1)[-1]
    key = re.sub(r'_(n|ne|e|se|s|sw|w|nw)_', '_<dir>_', name)
    key = re.sub(r'\d+', '#', key)
    family[key] += 1
for key, count in sorted(family.items()):
    print('   %-46s %d' % (key, count))

print()
print('which clips cite the art, and are those clips in a controller?')
clips = sorted({p for paths in referenced.values() for p in paths if p.endswith('.anim')})
controllers = [p for p in tree if p.endswith('.controller')]
controller_text = {c: git('cat-file', '-p', '%s:%s' % (REV, c)).decode('utf-8', 'replace')
                   for c in controllers}
for clip in clips:
    meta = git('cat-file', '-p', '%s:%s.meta' % (REV, clip)).decode('utf-8', 'replace')
    found = re.search(r'guid:\s*([0-9a-f]{32})', meta)
    clip_guid = found.group(1) if found else None
    holders = [c.rsplit('/', 1)[-1] for c, t in controller_text.items()
               if clip_guid and clip_guid in t]
    print('   %-44s -> %s' % (clip.rsplit('/', 1)[-1], holders or 'IN NO CONTROLLER'))
