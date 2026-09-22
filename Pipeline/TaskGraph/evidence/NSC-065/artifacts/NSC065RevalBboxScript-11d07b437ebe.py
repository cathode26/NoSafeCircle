"""Alpha bounding box of the four door source PNGs, read from main. Stdlib only."""
import struct
import subprocess
import zlib

REPO = r"C:/NSC/NSC/NoSafeCircle"
BASE = "Assets/NoSafeCircle/DoorPrototype/Art/Doors/Source"
NAMES = ["sealed", "locked", "open", "final", "broken", "damaged", "opening"]


def png_rgba(data):
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a png"
    pos, idat, w, h, depth, ctype = 8, b"", None, None, None, None
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        kind = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
            assert depth == 8 and ctype == 6 and interlace == 0, (depth, ctype, interlace)
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            break
        pos += 12 + length

    raw = zlib.decompress(idat)
    stride = w * 4
    out = bytearray(h * stride)
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        f = raw[p]
        p += 1
        line = bytearray(raw[p:p + stride])
        p += stride
        if f == 1:
            for i in range(4, stride):
                line[i] = (line[i] + line[i - 4]) & 0xFF
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif f == 3:
            for i in range(stride):
                a = line[i - 4] if i >= 4 else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif f == 4:
            for i in range(stride):
                a = line[i - 4] if i >= 4 else 0
                c = prev[i - 4] if i >= 4 else 0
                b = prev[i]
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return w, h, out


for name in NAMES:
    path = f"{BASE}/door_bonestone_{name}_S_000.png"
    blob = subprocess.run(["git", "-C", REPO, "show", f"main:{path}"],
                          capture_output=True, check=True).stdout
    w, h, px = png_rgba(blob)
    rows = [y for y in range(h)
            if any(px[(y * w + x) * 4 + 3] > 0 for x in range(w))]
    cols = [x for x in range(w)
            if any(px[(y * w + x) * 4 + 3] > 0 for y in range(h))]
    top, bottom = rows[0], rows[-1]
    left, right = cols[0], cols[-1]
    # Unity pivot y is measured from the BOTTOM of the canvas.
    ground_from_bottom = h - 1 - bottom
    pivot_y = ground_from_bottom / h
    print(f"{name:7s} {w}x{h}  opaque rows {top}-{bottom} (deepest {bottom}), "
          f"cols {left}-{right}  drawn {right-left+1}x{bottom-top+1}px  "
          f"rows below art: {ground_from_bottom}  pivot_y={pivot_y:.6f}  "
          f"height_world={(bottom-top+1)/64:.3f}u  width_world={(right-left+1)/64:.3f}u")
