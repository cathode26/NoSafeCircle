"""
Unit tests for ground_line.py. Stdlib unittest, synthetic images only,
no network, no real art. Run with:

    python -m unittest test_ground_line -v
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ground_line as gl  # noqa: E402


def make_frame_image(w, h, top, bottom, left=None, right=None, color=(10, 20, 30, 255)):
    """An RGBA image with one opaque rectangle spanning rows [top, bottom] inclusive."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if left is None:
        left = 0
    if right is None:
        right = w
    draw = ImageDraw.Draw(img)
    draw.rectangle([left, top, right - 1, bottom], fill=color)
    return img


def make_bounds_frame(group, direction, feet_row, head_row, reference_row, name=None):
    """A gl.Frame with pre-filled `measure`/`reference_row`, for compute_bounds()
    tests that don't need real image files (round 2)."""
    f = gl.Frame(group, direction, name or f"{direction}.png", "dummy-path")
    f.measure = {"feet_row": feet_row, "head_row": head_row, "opaque_pixels": 1}
    f.reference_row = reference_row
    return f


class TestPivotSanity(unittest.TestCase):
    def test_nsc077_pivot_sanity_case(self):
        # H 176, G_excl 132 (G inclusive = 131) -> pivot y 0.25 exactly.
        pivot = gl.compute_pivot(176, 131)
        self.assertEqual(pivot["x"], 0.5)
        self.assertEqual(pivot["y"], 0.25)


class TestLosslessShift(unittest.TestCase):
    def test_shift_preserves_opaque_count_and_moves_bbox_by_dy(self):
        img = make_frame_image(64, 64, top=20, bottom=30)
        before = gl.measure(img, "test")
        dy = 5
        shifted = gl.shift_image(img, dy, "test")
        after = gl.measure(shifted, "test-shifted")

        self.assertEqual(after["opaque_pixels"], before["opaque_pixels"])
        self.assertEqual(after["bbox"][1], before["bbox"][1] + dy)  # upper
        self.assertEqual(after["bbox"][3], before["bbox"][3] + dy)  # lower
        self.assertEqual(after["feet_row"], before["feet_row"] + dy)
        self.assertEqual(after["head_row"], before["head_row"] + dy)

    def test_negative_shift_also_lossless(self):
        img = make_frame_image(64, 64, top=20, bottom=30)
        before = gl.measure(img, "test")
        dy = -4
        shifted = gl.shift_image(img, dy, "test")
        after = gl.measure(shifted, "test-shifted")
        self.assertEqual(after["opaque_pixels"], before["opaque_pixels"])
        self.assertEqual(after["feet_row"], before["feet_row"] + dy)
        self.assertEqual(after["head_row"], before["head_row"] + dy)


class TestGSelection(unittest.TestCase):
    def _make_frame(self, group, direction, feet_row, head_row, reference_row):
        f = gl.Frame(group, direction, f"{direction}.png", "dummy-path")
        f.measure = {"feet_row": feet_row, "head_row": head_row, "opaque_pixels": 1}
        f.reference_row = reference_row
        return f

    def test_walk_dip_lowers_g_max_by_exactly_the_dip(self):
        canvas = 128
        # Baseline: two standing directions + a 3-frame walk group whose
        # feet all equal the group's reference (no dip).
        baseline = [
            self._make_frame("standing", "south", feet_row=100, head_row=40, reference_row=100),
            self._make_frame("standing", "north", feet_row=100, head_row=40, reference_row=100),
            self._make_frame("walk", "south-east", feet_row=100, head_row=40, reference_row=100),
            self._make_frame("walk", "south-east", feet_row=100, head_row=40, reference_row=100),
            self._make_frame("walk", "south-east", feet_row=100, head_row=40, reference_row=100),
        ]
        # bottom_margin=0 here to keep this test's original (round-1) intent —
        # it is exercising the walk-dip effect on g_max, not the margin.
        g_max0, g_min0, low0, high0, max_low0, max_high0 = gl.compute_bounds(baseline, canvas, 0, 0)
        self.assertEqual(max_low0, 0)
        self.assertEqual(g_max0, canvas - 1)

        # Same scenario, but one walk frame's foot dips 5px lower than its
        # group's reference (a forward foot stepping toward the camera).
        dipped = [
            self._make_frame("standing", "south", feet_row=100, head_row=40, reference_row=100),
            self._make_frame("standing", "north", feet_row=100, head_row=40, reference_row=100),
            self._make_frame("walk", "south-east", feet_row=100, head_row=40, reference_row=100),
            self._make_frame("walk", "south-east", feet_row=100, head_row=40, reference_row=100),
            self._make_frame("walk", "south-east", feet_row=105, head_row=40, reference_row=100),
        ]
        g_max1, g_min1, low1, high1, max_low1, max_high1 = gl.compute_bounds(dipped, canvas, 0, 0)
        self.assertEqual(max_low1, 5)
        self.assertEqual(g_max1, g_max0 - 5)
        self.assertIn("walk:south-east:south-east.png", low1)


class TestLowerMedian(unittest.TestCase):
    def test_odd_count(self):
        self.assertEqual(gl.lower_median([1, 3, 5]), 3)

    def test_even_count_picks_lower_of_the_two_middles(self):
        # sorted [1,2,3,4]; (4-1)//2 = 1 -> value 2 (the lower middle, not 3).
        self.assertEqual(gl.lower_median([4, 1, 3, 2]), 2)

    def test_even_count_with_repeats(self):
        # sorted [100,100,105,105]; (4-1)//2 = 1 -> value 100.
        self.assertEqual(gl.lower_median([105, 100, 105, 100]), 100)


class TestRefusals(unittest.TestCase):
    def test_shift_refuses_clip_at_top(self):
        img = make_frame_image(64, 64, top=0, bottom=5)
        with self.assertRaises(gl.ClipError):
            gl.shift_image(img, -3, "clip-top")

    def test_shift_refuses_clip_at_bottom(self):
        img = make_frame_image(64, 64, top=58, bottom=63)
        with self.assertRaises(gl.ClipError):
            gl.shift_image(img, 3, "clip-bottom")

    def test_g_max_below_g_min_writes_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            stills_dir = Path(td) / "stills"
            out_dir = Path(td) / "out"
            stills_dir.mkdir()
            out_dir.mkdir()
            img = make_frame_image(20, 20, top=15, bottom=18)
            img.save(stills_dir / "south.png")

            with self.assertRaises(gl.BoundsError):
                gl.run_plan(
                    key="refusal-test",
                    stills_dir=stills_dir,
                    walk_specs={},
                    out_dir=out_dir,
                    canvas=20,
                    top_margin=25,  # forces g_min (25) > g_max (19)
                )
            self.assertEqual(os.listdir(out_dir), [])


class TestCanvasMismatch(unittest.TestCase):
    def test_mixed_canvas_size_names_the_file(self):
        with tempfile.TemporaryDirectory() as td:
            stills_dir = Path(td) / "stills"
            stills_dir.mkdir()
            make_frame_image(128, 128, top=100, bottom=110).save(stills_dir / "south.png")
            bad_path = stills_dir / "north.png"
            make_frame_image(64, 64, top=50, bottom=55).save(bad_path)

            with self.assertRaises(gl.CanvasMismatchError) as ctx:
                gl.run_plan(
                    key="mismatch-test",
                    stills_dir=stills_dir,
                    walk_specs={},
                    out_dir=Path(td) / "out",
                    canvas=128,
                )
            self.assertIn(str(bad_path), str(ctx.exception))


class TestUnknownDirection(unittest.TestCase):
    def test_unknown_still_direction_is_an_error(self):
        with tempfile.TemporaryDirectory() as td:
            stills_dir = Path(td) / "stills"
            stills_dir.mkdir()
            make_frame_image(128, 128, top=100, bottom=110).save(stills_dir / "northnorth.png")
            with self.assertRaises(gl.UnknownDirectionError):
                gl.run_plan(
                    key="unknown-dir-test",
                    stills_dir=stills_dir,
                    walk_specs={},
                    out_dir=Path(td) / "out",
                    canvas=128,
                )


class TestCheck(unittest.TestCase):
    def _run_valid_plan(self, td):
        stills_dir = Path(td) / "stills"
        walk_dir = Path(td) / "walk_se"
        out_dir = Path(td) / "out"
        stills_dir.mkdir()
        walk_dir.mkdir()

        make_frame_image(128, 128, top=100, bottom=115).save(stills_dir / "south.png")
        make_frame_image(128, 128, top=98, bottom=112).save(stills_dir / "north.png")

        make_frame_image(128, 128, top=99, bottom=113).save(walk_dir / "frame_00.png")
        make_frame_image(128, 128, top=99, bottom=116).save(walk_dir / "frame_01.png")  # dip
        make_frame_image(128, 128, top=99, bottom=113).save(walk_dir / "frame_02.png")

        result = gl.run_plan(
            key="check-test",
            stills_dir=stills_dir,
            walk_specs={"south-east": str(walk_dir)},
            out_dir=out_dir,
            canvas=128,
        )
        return out_dir, result

    def test_check_passes_on_fresh_plan_output(self):
        with tempfile.TemporaryDirectory() as td:
            out_dir, _ = self._run_valid_plan(td)
            ok, problems = gl.run_check(out_dir / "ground_line.json")
            self.assertTrue(ok, msg=f"unexpected problems: {problems}")
            self.assertEqual(problems, [])

    def test_check_fails_after_a_frame_is_altered(self):
        with tempfile.TemporaryDirectory() as td:
            out_dir, _ = self._run_valid_plan(td)
            altered = out_dir / "standing" / "south.png"
            img = Image.open(altered).convert("RGBA")
            # Add one extra opaque pixel far from the existing content.
            img.putpixel((5, 5), (255, 0, 0, 255))
            img.save(altered)

            ok, problems = gl.run_check(out_dir / "ground_line.json")
            self.assertFalse(ok)
            self.assertTrue(any("south" in p for p in problems))


class TestBottomMargin(unittest.TestCase):
    """Round 2: --bottom-margin keeps the ground line off the canvas' bottom edge."""

    def test_bottom_margin_shifts_g_max_down_by_exactly_n(self):
        canvas = 128
        frames = [
            make_bounds_frame("standing", "south", feet_row=100, head_row=40, reference_row=100),
            make_bounds_frame("standing", "north", feet_row=100, head_row=40, reference_row=100),
        ]
        g_max0, *_ = gl.compute_bounds(frames, canvas, 0, 0)
        g_max2, *_ = gl.compute_bounds(frames, canvas, 0, 2)
        g_max5, *_ = gl.compute_bounds(frames, canvas, 0, 5)
        self.assertEqual(g_max2, g_max0 - 2)
        self.assertEqual(g_max5, g_max0 - 5)

    def test_dry_run_like_case_moves_from_122_to_120(self):
        # Same shape as the job's stated dry-run regression: canvas 128, a walk
        # frame dipping 5px below its group's reference (max_low=5). With
        # bottom_margin=0 (round 1's implicit behaviour) g_max=122; with the
        # new default bottom_margin=2, g_max=120.
        canvas = 128
        frames = [
            make_bounds_frame("standing", "south", feet_row=100, head_row=40, reference_row=100),
            make_bounds_frame("walk", "south-east", feet_row=100, head_row=40,
                               reference_row=100, name="frame_00.png"),
            make_bounds_frame("walk", "south-east", feet_row=105, head_row=40,
                               reference_row=100, name="frame_06.png"),
        ]
        g_max_old, *_ = gl.compute_bounds(frames, canvas, 0, 0)
        g_max_new, *_ = gl.compute_bounds(frames, canvas, 0, 2)
        self.assertEqual(g_max_old, 122)
        self.assertEqual(g_max_new, 120)


class TestDipMeasurement(unittest.TestCase):
    """Round 2: per-group dip_below_ground_line / deepest_row_* / deepest_frames."""

    def test_dip_zero_when_group_frames_all_at_reference(self):
        with tempfile.TemporaryDirectory() as td:
            walk_dir = Path(td) / "walk_se"
            out_dir = Path(td) / "out"
            walk_dir.mkdir()
            for i in range(3):
                make_frame_image(128, 128, top=99, bottom=113).save(walk_dir / f"frame_0{i}.png")

            result = gl.run_plan(
                key="dip-zero-test",
                stills_dir=None,
                walk_specs={"south-east": str(walk_dir)},
                out_dir=out_dir,
                canvas=128,
            )
            walk_entry = result["directions"]["south-east"]["walk"]
            self.assertEqual(walk_entry["dip_below_ground_line"], 0)
            self.assertEqual(
                walk_entry["deepest_row_after"],
                walk_entry["reference_row"] + walk_entry["dy"],
            )

    def test_dip_matches_one_deeper_frame(self):
        with tempfile.TemporaryDirectory() as td:
            walk_dir = Path(td) / "walk_se"
            out_dir = Path(td) / "out"
            walk_dir.mkdir()
            make_frame_image(128, 128, top=99, bottom=113).save(walk_dir / "frame_00.png")
            make_frame_image(128, 128, top=99, bottom=118).save(walk_dir / "frame_01.png")  # dips 5px
            make_frame_image(128, 128, top=99, bottom=113).save(walk_dir / "frame_02.png")

            result = gl.run_plan(
                key="dip-five-test",
                stills_dir=None,
                walk_specs={"south-east": str(walk_dir)},
                out_dir=out_dir,
                canvas=128,
            )
            walk_entry = result["directions"]["south-east"]["walk"]
            self.assertEqual(walk_entry["dip_below_ground_line"], 5)
            self.assertEqual(walk_entry["deepest_frames"], ["frame_01.png"])


class TestMaxDipCap(unittest.TestCase):
    """Round 2: --max-dip / --no-max-dip."""

    def _make_dip_scenario(self, td, deep_bottom):
        walk_dir = Path(td) / "walk_se"
        out_dir = Path(td) / "out"
        walk_dir.mkdir()
        out_dir.mkdir()
        make_frame_image(128, 128, top=99, bottom=113).save(walk_dir / "frame_00.png")
        make_frame_image(128, 128, top=99, bottom=deep_bottom).save(walk_dir / "frame_01.png")
        make_frame_image(128, 128, top=99, bottom=113).save(walk_dir / "frame_02.png")
        return walk_dir, out_dir

    def test_dip_over_cap_refuses_writes_nothing_and_names_group(self):
        with tempfile.TemporaryDirectory() as td:
            walk_dir, out_dir = self._make_dip_scenario(td, deep_bottom=123)  # dip=10
            with self.assertRaises(gl.MaxDipExceededError) as ctx:
                gl.run_plan(
                    key="dip-cap-test",
                    stills_dir=None,
                    walk_specs={"south-east": str(walk_dir)},
                    out_dir=out_dir,
                    canvas=128,
                )
            msg = str(ctx.exception)
            self.assertIn("south-east:walk", msg)
            self.assertIn("dip=10", msg)
            self.assertIn("frame_01.png", msg)
            self.assertEqual(os.listdir(out_dir), [])

    def test_dip_exactly_equal_to_cap_is_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            walk_dir, out_dir = self._make_dip_scenario(td, deep_bottom=118)  # dip=5
            result = gl.run_plan(
                key="dip-cap-equal-test",
                stills_dir=None,
                walk_specs={"south-east": str(walk_dir)},
                out_dir=out_dir,
                canvas=128,
                max_dip=5,
            )
            self.assertEqual(result["max_dip_observed"], 5)
            self.assertEqual(result["max_dip"], 5)

    def test_no_max_dip_accepts_any_dip(self):
        with tempfile.TemporaryDirectory() as td:
            walk_dir, out_dir = self._make_dip_scenario(td, deep_bottom=123)  # dip=10, over default cap
            result = gl.run_plan(
                key="dip-no-cap-test",
                stills_dir=None,
                walk_specs={"south-east": str(walk_dir)},
                out_dir=out_dir,
                canvas=128,
                no_max_dip=True,
            )
            self.assertEqual(result["max_dip_observed"], 10)
            self.assertIsNone(result["max_dip"])


class TestCheckDipMismatch(unittest.TestCase):
    """Round 2: check() re-derives and verifies the per-group dip fields."""

    def test_check_fails_when_dip_below_ground_line_is_edited_wrong(self):
        with tempfile.TemporaryDirectory() as td:
            walk_dir = Path(td) / "walk_se"
            out_dir = Path(td) / "out"
            walk_dir.mkdir()
            make_frame_image(128, 128, top=99, bottom=113).save(walk_dir / "frame_00.png")
            make_frame_image(128, 128, top=99, bottom=118).save(walk_dir / "frame_01.png")  # dip 5
            make_frame_image(128, 128, top=99, bottom=113).save(walk_dir / "frame_02.png")

            gl.run_plan(
                key="dip-check-mismatch-test",
                stills_dir=None,
                walk_specs={"south-east": str(walk_dir)},
                out_dir=out_dir,
                canvas=128,
            )

            json_path = out_dir / "ground_line.json"
            data = json.loads(json_path.read_text(encoding="utf-8"))
            data["directions"]["south-east"]["walk"]["dip_below_ground_line"] = 999
            json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

            ok, problems = gl.run_check(json_path)
            self.assertFalse(ok)
            self.assertTrue(
                any("south-east:walk" in p and "dip_below_ground_line" in p for p in problems),
                msg=f"problems: {problems}",
            )


if __name__ == "__main__":
    unittest.main()
