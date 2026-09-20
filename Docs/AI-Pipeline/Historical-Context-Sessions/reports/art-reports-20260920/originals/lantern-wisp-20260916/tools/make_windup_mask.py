"""Build the binary inpaint mask for the Lantern Wraith wind-up frame.

White = regenerate, black = keep (Pro Flash inpaint contract). Two rectangles:
- lantern and a small halo margin: x 89..118, y 18..47 (30x30);
- hood interior (bone rim, dark face, teal eyes): x 55..80, y 33..60 (26x28).
The mask is a generation parameter, not art. Prints its base64 for the tool call.
"""
import base64
import hashlib
import io
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "inputs" / "windup_mask_128.png"
RECTS = {
    "lantern_halo": (89, 18, 30, 30),
    "hood_interior": (55, 33, 26, 28),
}


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    mask = Image.new("RGB", (128, 128), (0, 0, 0))
    draw = ImageDraw.Draw(mask)
    for x, y, w, h in RECTS.values():
        draw.rectangle([x, y, x + w - 1, y + h - 1], fill=(255, 255, 255))
    buffer = io.BytesIO()
    mask.save(buffer, format="PNG", optimize=True)
    data = buffer.getvalue()
    OUT.write_bytes(data)
    white = sum(1 for value in mask.getchannel("R").getdata() if value == 255)
    print("mask", OUT, "white pixels", white, "sha256", hashlib.sha256(data).hexdigest())
    print("base64", base64.b64encode(data).decode("ascii"))


if __name__ == "__main__":
    main()
