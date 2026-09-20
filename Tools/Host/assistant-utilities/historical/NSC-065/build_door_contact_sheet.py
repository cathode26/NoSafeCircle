from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(r"C:\NSC\NoSafeCircle-AssistantCheckouts\NSC-065\Docs\Art\Doors")
STATES = ("sealed", "opening", "open", "locked", "damaged", "broken", "final")
FAMILIES = (("family_a", "Family A — iron and wood"), ("family_b", "Family B — bone and stone"))

font = ImageFont.load_default()
cell_w, cell_h = 160, 170
left, top = 190, 38
sheet = Image.new("RGBA", (left + cell_w * len(STATES), top + cell_h * len(FAMILIES)), "#202329")
draw = ImageDraw.Draw(sheet)

for column, state in enumerate(STATES):
    draw.text((left + column * cell_w + 8, 12), state, fill="#f2f4f8", font=font)

for row, (folder, label) in enumerate(FAMILIES):
    y = top + row * cell_h
    draw.text((12, y + 72), label, fill="#f2f4f8", font=font)
    for column, state in enumerate(STATES):
        image = Image.open(ROOT / "Candidates" / folder / f"{state}.png").convert("RGBA")
        image.thumbnail((128, 128), Image.Resampling.NEAREST)
        x = left + column * cell_w + (cell_w - image.width) // 2
        py = y + 20 + (128 - image.height) // 2
        sheet.alpha_composite(image, (x, py))
        draw.rectangle((left + column * cell_w, y, left + (column + 1) * cell_w - 1, y + cell_h - 1), outline="#454b55")

sheet.convert("RGB").save(ROOT / "contact_sheet.png", quality=95)
