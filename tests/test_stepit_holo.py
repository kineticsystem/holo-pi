"""Tests the calibration, the layout, the interleaving, the test quilt and the command line, without a display."""

import contextlib
import io
import json
import math
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image

from stepit_holo import Interleaver, Layout, interleave, load_calibration, numbers_quilt
from stepit_holo.calibration import Calibration, find_calibration
from stepit_holo.cli import main

HERE = Path(__file__).parent
VISUAL = HERE / "portrait_visual.json"
PORTRAIT = Layout(8, 6)


def numbered_quilt(layout=PORTRAIT, width=42, height=56):
    """A quilt whose view v is filled with the value v + 1, view 0 at the bottom left."""
    quilt = np.zeros((layout.rows * height, layout.columns * width, 3), np.uint8)
    for v in range(layout.views):
        row, column = layout.rows - 1 - v // layout.columns, v % layout.columns
        quilt[row * height:(row + 1) * height, column * width:(column + 1) * width] = v + 1
    return quilt


class CalibrationTest(unittest.TestCase):
    def test_reads_visual_json_as_looking_glass_does(self):
        cal = load_calibration(VISUAL)
        self.assertEqual((cal.width, cal.height, cal.serial), (1536, 2048, "LKG-PORT-00000"))
        slope = -7.161397095759771
        self.assertAlmostEqual(cal.pitch, 52.58790040712976 * 1536 / 324 * math.cos(math.atan(1 / slope)))
        self.assertAlmostEqual(cal.tilt, 2048 / (1536 * slope))
        self.assertAlmostEqual(cal.subp, 1 / (1536 * 3))
        self.assertAlmostEqual(cal.center, 0.7432299004945404)
        self.assertTrue(cal.inverted)

    def test_a_mirrored_screen_slants_the_other_way(self):
        values = json.loads(VISUAL.read_text())
        mirrored = Calibration.from_visual(dict(values, flipImageX={"value": 1}))
        normal = Calibration.from_visual(values)
        self.assertAlmostEqual(mirrored.tilt, -normal.tilt)
        self.assertAlmostEqual(mirrored.subp, -normal.subp)

    def test_finds_the_drive_of_a_looking_glass(self):
        with tempfile.TemporaryDirectory() as mount:
            folder = Path(mount, "robot", "LKG-P00000", "LKG_calibration")
            folder.mkdir(parents=True)
            (folder / "visual.json").write_text(VISUAL.read_text())
            self.assertEqual(find_calibration([mount]).serial, "LKG-PORT-00000")

    def test_says_what_to_check_when_there_is_none(self):
        with tempfile.TemporaryDirectory() as mount, self.assertRaisesRegex(RuntimeError, "USB cable"):
            find_calibration([mount])


class LayoutTest(unittest.TestCase):
    def test_reads_the_layout_from_the_name(self):
        self.assertEqual(Layout.from_name("wasp_qs8x6a0.75.jpg"), Layout(8, 6))
        self.assertEqual(Layout.from_name("/a/b/sample_qs7x11a1.8.png"), Layout(7, 11))
        self.assertEqual(Layout.from_name("x_qs5x9.png"), Layout(5, 9))
        self.assertIsNone(Layout.from_name("wasp.jpg"))


class InterleaveTest(unittest.TestCase):
    def setUp(self):
        self.calibration = load_calibration(VISUAL)

    def test_fills_the_screen(self):
        hologram = interleave(numbered_quilt(), PORTRAIT, self.calibration, cache=False)
        self.assertEqual(hologram.shape, (2048, 1536, 3))
        self.assertEqual(hologram.dtype, np.uint8)

    def test_each_sub_pixel_takes_one_view_and_every_view_is_seen(self):
        hologram = interleave(numbered_quilt(), PORTRAIT, self.calibration, cache=False)
        self.assertEqual(list(np.unique(hologram)), list(range(1, 49)))

    def test_takes_the_same_views_as_the_implementation_checked_through_the_lens(self):
        reference = json.loads((HERE / "reference_views.json").read_text())["samples"]
        hologram = interleave(numbered_quilt(width=420, height=560), PORTRAIT, self.calibration, cache=False)
        same = sum(int(hologram[row, column, subpixel]) - 1 == view for row, column, subpixel, view in reference)
        # Rounding may differ between processors at the edge between two views: a few, not more.
        self.assertGreaterEqual(same / len(reference), 0.99)

    def test_inverted_and_reversed_views_go_the_other_way(self):
        quilt = numbered_quilt()
        normal = interleave(quilt, PORTRAIT, self.calibration, cache=False).astype(int)
        for other in [interleave(quilt, PORTRAIT, replace(self.calibration, inverted=False), cache=False),
                      interleave(quilt, PORTRAIT, self.calibration, reverse=True, cache=False)]:
            # View v for view 47 - v, give or take one at the edge between two views.
            self.assertGreater(np.mean(np.abs(normal - 1 + other.astype(int) - 1 - 47) <= 1), 0.99)

    def test_caches_the_table_and_reuses_it(self):
        with tempfile.TemporaryDirectory() as cache, mock.patch.dict(os.environ, {"XDG_CACHE_HOME": cache}):
            first = Interleaver(self.calibration, PORTRAIT, 336, 336)
            self.assertEqual(len(list(Path(cache, "stepit-holo").glob("table-*.npy"))), 1)
            with mock.patch("stepit_holo.interleave.table", side_effect=AssertionError("computed again")):
                second = Interleaver(self.calibration, PORTRAIT, 336, 336)
            np.testing.assert_array_equal(first.table, second.table)

    def test_refuses_a_quilt_of_another_size(self):
        interleaver = Interleaver(self.calibration, PORTRAIT, 336, 336, cache=False)
        with self.assertRaises(ValueError):
            interleaver(np.zeros((100, 100, 3), np.uint8))


class NumbersTest(unittest.TestCase):
    def test_a_portrait_quilt_of_48_views_each_its_own_colour(self):
        quilt = numbers_quilt()
        self.assertEqual(quilt.shape, (3360, 3360, 3))
        # The background of each view, at its top left corner: 48 colours.
        corners = {tuple(quilt[row * 560 + 5, column * 420 + 5]) for row in range(6) for column in range(8)}
        self.assertEqual(len(corners), 48)

    def test_draws_the_number(self):
        quilt = numbers_quilt()
        # View 1, at the bottom left, has black in its middle: the digit.
        view_1 = quilt[5 * 560:, :420]
        self.assertTrue((view_1[200:360, 150:270] == 0).all(axis=2).any())


class CommandLineTest(unittest.TestCase):
    def run_main(self, *arguments):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = main(list(arguments))
        return code, output.getvalue()

    def test_render_saves_the_hologram(self):
        with tempfile.TemporaryDirectory() as folder:
            quilt = Path(folder, "test_qs8x6a0.75.png")
            Image.fromarray(numbered_quilt()).save(quilt)
            hologram = Path(folder, "hologram.png")
            code, _ = self.run_main("render", str(quilt), "-o", str(hologram), "--calibration", str(VISUAL))
            self.assertEqual(code, 0)
            self.assertEqual(Image.open(hologram).size, (1536, 2048))

    def test_render_needs_a_layout(self):
        with tempfile.TemporaryDirectory() as folder:
            quilt = Path(folder, "test.png")
            Image.fromarray(numbered_quilt()).save(quilt)
            code, output = self.run_main("render", str(quilt), "-o", str(Path(folder, "h.png")),
                                         "--calibration", str(VISUAL))
            self.assertEqual(code, 1)
            self.assertIn("--columns and --rows", output)

    def test_numbers_saves_the_test_quilt(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "numbers_qs8x6a0.75.png")
            code, _ = self.run_main("numbers", "--quilt-output", str(path))
            self.assertEqual(code, 0)
            self.assertEqual(Image.open(path).size, (3360, 3360))

    def test_calibration_prints_the_values(self):
        code, output = self.run_main("calibration", "--calibration", str(VISUAL))
        self.assertEqual(code, 0)
        self.assertIn("width: 1536", output)
        self.assertIn("serial: LKG-PORT-00000", output)

    def test_the_demo_quilt_is_a_portrait_quilt(self):
        demo = HERE.parent / "quilts" / "wasp_qs8x6a0.75.jpg"
        self.assertEqual(Layout.from_name(demo), PORTRAIT)
        self.assertEqual(Image.open(demo).size, (3360, 3360))


if __name__ == "__main__":
    unittest.main()
