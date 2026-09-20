"""Add a WorldSprites sorting layer to TagManager.asset, preserving CRLF."""
import sys

path = r'C:\nscrev\branch-verify\ProjectSettings\TagManager.asset'
data = open(path, 'rb').read()

anchor = b"  m_SortingLayers:\r\n  - name: Default\r\n    uniqueID: 0\r\n    locked: 0\r\n"
addition = b"  - name: WorldSprites\r\n    uniqueID: 1043912875\r\n    locked: 0\r\n"

if data.count(anchor) != 1:
    print('ABORT: anchor found %d times' % data.count(anchor))
    sys.exit(1)
if b'WorldSprites' in data:
    print('ABORT: WorldSprites already present')
    sys.exit(1)

data = data.replace(anchor, anchor + addition)
open(path, 'wb').write(data)
print('added; bytes=%d lone_lf=%d' % (len(data), data.count(b'\n') - data.count(b'\r\n')))
