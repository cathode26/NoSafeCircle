"""Windows-only probes for the fix round: output-vs-input collisions through case changes,
forward/back slashes and 8.3 short names. Works on copies only; runs the CLI in-process."""
import hashlib
import os
import shutil
import sys
from pathlib import Path

PACKAGE = Path(r"C:\nscrev\codex-jobs\codex-art-review-toolkit-20260917-0021\Pipeline\ArtReview")
sys.path.insert(0, str(PACKAGE))
sys.dont_write_bytecode = True
from art_review.cli import main  # noqa: E402

HERE = Path(__file__).resolve().parent / "collision_probe_round2"
HERE.mkdir(exist_ok=True)
shutil.copyfile(r"C:\NSC\NSC\NoSafeCircle\Assets\NoSafeCircle\DoorPrototype\Art\Enemies\Source\enemy_ranged_se_idle_00.png", HERE / "source.png")
shutil.copyfile(r"C:\nscrev\reports\art-director\lantern-wisp-20260916\pixellab\windup_se_128.png", HERE / "result.png")
shutil.copyfile(r"C:\nscrev\reports\art-director\lantern-wisp-20260916\inputs\windup_mask_128.png", HERE / "mask.png")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def short_name(path):
    import ctypes
    buffer = ctypes.create_unicode_buffer(512)
    ctypes.windll.kernel32.GetShortPathNameW(str(path), buffer, 512)
    return buffer.value or str(path)


source = HERE / "source.png"
original = sha(source)
variants = {
    "upper-case": str(source).upper(),
    "forward-slashes": str(source).replace("\\", "/"),
    "8.3-short-name": short_name(source),
    "dot-segment": str(HERE / "." / "source.png"),
}
ok = True
for label, output in variants.items():
    code = main(["mask-diff", "--source", str(source), "--result", str(HERE / "result.png"), "--mask", str(HERE / "mask.png"), "--output", output])
    unchanged = sha(source) == original
    passed = code == 2 and unchanged
    ok &= passed
    print(("PASS " if passed else "FAIL ") + f"{label}: exit {code}, source unchanged {unchanged}, output arg {output}")

# A legitimate distinct output must still work.
code = main(["mask-diff", "--source", str(source), "--result", str(HERE / "result.png"), "--mask", str(HERE / "mask.png"), "--output", str(HERE / "proof.png")])
print(("PASS " if code == 0 and (HERE / "proof.png").exists() else "FAIL ") + f"distinct output: exit {code}")
ok &= code == 0

# normalize into the source folder with the same file name must be refused.
frames_dir = HERE / "frames"
frames_dir.mkdir(exist_ok=True)
shutil.copyfile(r"C:\nscrev\reports\art-director\density-trial-20260916\pixellab\3c_walk_se_raw\frame_01.png", frames_dir / "frame_01.png")
before = sha(frames_dir / "frame_01.png")
code = main(["normalize", str(frames_dir / "frame_01.png"), "--size", "128", "--output-dir", str(frames_dir).upper()])
unchanged = sha(frames_dir / "frame_01.png") == before
print(("PASS " if code != 0 and unchanged else "FAIL ") + f"normalize into its own folder (upper-case dir): exit {code}, source unchanged {unchanged}")
ok &= code != 0 and unchanged
print("ALL PASS" if ok else "SOME FAILED")
