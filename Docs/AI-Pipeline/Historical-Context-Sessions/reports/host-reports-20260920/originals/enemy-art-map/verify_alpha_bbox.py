"""Verify the Documentation Agent's correction: is the DRAWN figure the same size in idle and walk?

My earlier claim compared canvas sizes (128 vs 176) and concluded a 38% size pop. If the 176 canvas
is transparent rotation padding, the drawn figure will be nearly identical and my claim was wrong -
and the PPU 88 'fix' would have shrunk the walking figure instead.
"""
import io
import subprocess

from PIL import Image

GIT_DIR = r'C:\NSC\NSC\NoSafeCircle\.git'
NO_WINDOW = 0x08000000
BASE = 'Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source'

TARGETS = [
    ('melee  idle  s', BASE + '/enemy_melee_s_idle_00.png'),
    ('melee  walk  s0', BASE + '/Walk/enemy_melee_s_walk_00.png'),
    ('ranged idle  s', BASE + '/enemy_ranged_s_idle_00.png'),
    ('ranged walk  s0', BASE + '/Walk/enemy_ranged_s_walk_00.png'),
]


def blob(path):
    return subprocess.run(['git', '--git-dir', GIT_DIR, 'cat-file', '-p', 'main:' + path],
                          capture_output=True, creationflags=NO_WINDOW).stdout


def meta_value(path, key):
    text = blob(path + '.meta').decode('utf-8', 'replace')
    for line in text.splitlines():
        if key in line:
            return line.strip()
    return '(not found)'


print('%-16s %-8s %-12s %-12s %-10s' % ('sprite', 'canvas', 'figure w x h', 'ground row', 'height/64'))
rows = []
for label, path in TARGETS:
    data = blob(path)
    if not data:
        print('%-16s MISSING at main' % label)
        continue
    image = Image.open(io.BytesIO(data)).convert('RGBA')
    bbox = image.getbbox()  # alpha-aware bounding box
    if bbox is None:
        print('%-16s fully transparent' % label)
        continue
    left, top, right, bottom = bbox
    width, height = right - left, bottom - top
    rows.append((label, image.width, width, height, bottom))
    print('%-16s %-8s %-12s %-12s %.3f' % (
        label, image.width, '%dx%d' % (width, height), bottom, height / 64.0))

print()
if len(rows) >= 2:
    idle_h = rows[0][3]
    walk_h = rows[1][3]
    print('melee drawn height idle %d px vs walk %d px -> %.1f%% difference'
          % (idle_h, walk_h, (walk_h / idle_h - 1) * 100))
    print('canvas-based claim was 128 -> 176, i.e. 37.5%%: %s'
          % ('WRONG, the padding is transparent' if abs(walk_h / idle_h - 1) < 0.1 else 'supported'))
    print()
    print('what PPU 88 would have done to the walk frames:')
    print('  walk drawn height %d px at PPU 88 = %.2f units' % (walk_h, walk_h / 88.0))
    print('  idle drawn height %d px at PPU 64 = %.2f units' % (idle_h, idle_h / 64.0))
    print('  -> %.0f%% change when walking, in the OTHER direction'
          % ((walk_h / 88.0) / (idle_h / 64.0) * 100 - 100))

print()
print('pivots, which are what actually place the feet:')
for label, path in TARGETS:
    print('  %-16s %s' % (label, meta_value(path, 'spritePivot')))
