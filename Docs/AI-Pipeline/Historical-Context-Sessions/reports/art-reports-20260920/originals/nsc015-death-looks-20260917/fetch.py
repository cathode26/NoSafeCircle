"""Download the NSC-015 death sprites, measure them, and note the ground line each will need."""
import hashlib, json, os, sys, time, urllib.error, urllib.request
from PIL import Image

O = "C:/nscrev/reports/art-director/nsc015-death-looks-20260917/samples"
OBJECTS = [
    ("death_brute_blasted", "4423f1d2-08ee-44d8-ba0a-c81abeeb95f0", 40001),
    ("death_brute_burned", "a102f7b2-29c4-4747-8d08-687a2e71bce0", 40002),
    ("death_brute_decapitated", "693166c8-0c4e-471f-84a1-bd7faf8a13e1", 40003),
    ("death_brute_dismembered", "1a791813-e690-4431-a7b8-49959eeee6ea", 40004),
    ("death_wraith_dissipated", "56059dfa-96a2-4529-8606-14004efd373d", 40005),
    ("death_wraith_snuffed", "e8c7d38f-3a15-4386-b5cb-23ef8a835577", 40006),
    ("death_wraith_shattered", "6da672cb-9ad2-427a-9473-60f124c686d2", 40007),
    ("death_wraith_unravelled", "89f40548-a7dc-48c6-aba9-520158027751", 40008),
]


def fetch(oid, tries=10, wait=25):
    url = f"https://api.pixellab.ai/mcp/objects/{oid}/download"
    for n in range(tries):
        try:
            return urllib.request.urlopen(url, timeout=180).read()
        except urllib.error.HTTPError as e:
            if e.code in (423, 404):
                print("   still generating, waiting")
                time.sleep(wait)
                continue
            raise
    return None


def main():
    os.makedirs(O, exist_ok=True)
    recs = []
    for name, oid, seed in OBJECTS:
        p = f"{O}/{name}.png"
        if not os.path.exists(p):
            d = fetch(oid)
            if d is None:
                print(name, "GAVE UP")
                continue
            open(p, "wb").write(d)
        data = open(p, "rb").read()
        im = Image.open(p).convert("RGBA")
        a = im.getchannel("A")
        al = a.load()
        rows = [y for y in range(im.height) if any(al[x, y] > 8 for x in range(im.width))]
        recs.append({"name": name, "object_id": oid, "seed": seed, "canvas": list(im.size),
                     "alpha_bbox": list(a.getbbox()), "lowest_opaque_row": rows[-1],
                     "colours": len({c for c in im.getdata() if c[3] > 8}),
                     "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
        r = recs[-1]
        print(f"{name:26s} {r['canvas']} bbox {str(r['alpha_bbox']):22s} ground {r['lowest_opaque_row']:3d} "
              f"colours {r['colours']:5d}")
    json.dump(recs, open(f"{O}/../measurements.json", "w"), indent=2)
    if recs:
        g = [r["lowest_opaque_row"] for r in recs]
        print(f"\nground-line spread across the set: {max(g) - min(g)} px "
              f"(min {min(g)}, max {max(g)}) - plant_feet.py normalises this at zero cost")


main()
