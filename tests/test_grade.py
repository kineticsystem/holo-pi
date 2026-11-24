"""Tests the grades: their values, and the GPU's grading, off screen, skipped without EGL and OpenGL ES 3."""

import unittest

import numpy as np

from holo_pi import Interleaver
from holo_pi.grade import BAND_HUES, BY_ID, PARAMETERS, SPATIAL, Grade, mixer, tone_curve, white_balance
from test_holo_pi import PORTRAIT

try:
    from test_gl import CALIBRATION, OFFSCREEN  # The same: a second context would take the place of the first.
except unittest.SkipTest as skipped:  # No GPU, or no EGL: e.g. a computer without a graphics driver.
    OFFSCREEN, NO_GPU = None, str(skipped)
else:
    NO_GPU = ""

VIEW = (60, 80)  # The width and height of a view of the test quilts, small enough for a quick test.


def quilt_of(view):
    """A quilt whose every view is this one."""
    return np.tile(np.asarray(view, np.uint8), (PORTRAIT.rows, PORTRAIT.columns, 1))


def flat(*colour):
    return np.full((VIEW[1], VIEW[0], 3), colour, np.uint8)


def ramps():
    """A view of every grey, light and dark colours: what a grade at its defaults must not change."""
    y, x = np.mgrid[0:VIEW[1], 0:VIEW[0]]
    return np.stack([x * 255 // (VIEW[0] - 1), y * 255 // (VIEW[1] - 1), (x + y) * 255 // sum(VIEW)], -1)


class GradeTest(unittest.TestCase):
    def test_every_parameter_has_its_own_id_and_a_default_in_its_range(self):
        self.assertEqual(len(BY_ID), len(PARAMETERS))
        for parameter in PARAMETERS:
            self.assertLess(parameter.minimum, parameter.maximum)
            self.assertTrue(parameter.minimum <= parameter.default <= parameter.maximum, parameter.id)
        self.assertTrue(set(SPATIAL) <= set(BY_ID))

    def test_the_parameters_of_a_section_are_together(self):
        sections = [parameter.section for parameter in PARAMETERS]
        starts = [section for before, section in zip([None] + sections, sections) if section != before]
        self.assertEqual(len(starts), len(set(starts)))

    def test_a_grade_at_its_defaults_changes_nothing_and_is_not_kept(self):
        for grade in (Grade.of(None), Grade.of({}), Grade.of({"exposure": 0, "shadow_split": 25})):
            self.assertFalse(grade.changes)
            self.assertIsNone(grade.kept)

    def test_keeps_what_differs_from_the_defaults(self):
        grade = Grade.of({"exposure": 1.5, "contrast": 0, "unknown": 3})
        self.assertEqual(grade.kept, {"exposure": 1.5, "enabled": True})
        self.assertEqual(Grade.of(grade.kept), grade)
        self.assertEqual((grade["exposure"], grade["contrast"], grade.full["midtone_split"]), (1.5, 0, 50))

    def test_puts_the_values_in_their_ranges(self):
        grade = Grade.of({"exposure": 99, "sharpness": -5, "contrast": float("nan")})
        self.assertEqual(grade.values, {"exposure": 5})

    def test_a_grade_switched_off_changes_nothing_and_is_kept(self):
        grade = Grade.of({"exposure": 1, "enabled": False})
        self.assertFalse(grade.changes)
        self.assertEqual(grade.kept, {"exposure": 1, "enabled": False})

    def test_the_splits_alone_change_nothing(self):
        self.assertFalse(Grade.of({"shadow_split": 40}).changes)

    def test_the_white_balance_at_its_defaults_changes_nothing(self):
        np.testing.assert_allclose(white_balance(0, 0), np.eye(3), atol=1e-12)

    def test_a_warmer_white_balance_lifts_red_and_lowers_blue(self):
        red, green, blue = white_balance(50, 0) @ np.ones(3)
        self.assertGreater(red, green)
        self.assertGreater(green, blue)

    def test_the_tone_curve_always_rises(self):
        for amounts in ((100, -100, 100, -100), (-100, 100, -100, 100), (0, 0, 0, 0)):
            zones = ("shadows", "darks", "lights", "highlights")
            x, y, tangents = tone_curve(Grade.of({f"curve_{zone}": a for zone, a in zip(zones, amounts)}))
            self.assertTrue((np.diff(x) > 0).all() and (np.diff(y) > 0).all() and (tangents >= 0).all())

    def test_the_mixers_bands_follow_each_other(self):
        self.assertTrue((np.diff(BAND_HUES) > 0).all())
        turns, chromas, stops = mixer(Grade.of({"aqua_hue": 50, "red_luminance": -100}))
        self.assertEqual((turns[4], stops[0], chromas.any()), (15, -1, False))


@unittest.skipIf(OFFSCREEN is None, NO_GPU)
class GpuGradeTest(unittest.TestCase):
    renderer = OFFSCREEN and OFFSCREEN.renderer

    def draw(self, view, **values):
        """The hologram of a quilt of this view, graded."""
        self.renderer.quilt(quilt_of(view), PORTRAIT, CALIBRATION, grade=Grade.of(values))
        return self.renderer.read().astype(int)

    def colour(self, view, **values):
        """The one colour of the hologram of a flat view, graded: the same on every pixel."""
        pixels = self.draw(view, **values).reshape(-1, 3)
        np.testing.assert_array_equal(pixels.min(0), pixels.max(0))
        return pixels[0]

    def test_almost_nothing_changes_almost_nothing(self):
        # Through the table, and the tools that look around: at most one level from the quilt as it is.
        plain = self.draw(ramps())
        for tool in ("exposure", "sharpness", "shadows"):
            self.assertLessEqual(np.abs(self.draw(ramps(), **{tool: 1e-4}) - plain).max(), 1)

    def test_interleaves_as_the_processor(self):
        quilt = np.random.default_rng(1).integers(0, 256, (6 * 80, 8 * 60, 3), dtype=np.uint8)
        hologram = Interleaver(CALIBRATION, PORTRAIT, 480, 480, reverse=True, cache=False)(quilt)
        self.renderer.quilt(quilt, PORTRAIT, CALIBRATION, True, Grade.of({"exposure": 1e-4}))
        # A few sub-pixels at the edge between two views differ, as without a grade.
        close = np.abs(self.renderer.read().astype(int) - hologram) <= 1
        self.assertGreaterEqual(close.mean(), 0.999)

    def test_a_stop_is_twice_the_light(self):
        # 99 in sRGB is 0.1248 linear, twice is 0.2496, 137.
        np.testing.assert_allclose(self.colour(flat(99, 99, 99), exposure=1), 137, atol=1)

    def test_no_saturation_is_black_and_white(self):
        colour = self.colour(flat(200, 60, 30), saturation=-100)
        self.assertLessEqual(colour.max() - colour.min(), 1)

    def test_contrast_keeps_middle_grey(self):
        np.testing.assert_allclose(self.colour(flat(118, 118, 118), contrast=100), 118, atol=1)
        self.assertLess(self.colour(flat(50, 50, 50), contrast=100)[0], 45)
        self.assertGreater(self.colour(flat(200, 200, 200), contrast=100)[0], 205)

    def test_a_warmer_white_balance_is_warmer(self):
        red, green, blue = self.colour(flat(128, 128, 128), temperature=60)
        self.assertTrue(red > green > blue, (red, green, blue))

    def test_the_blacks_lift_and_sink(self):
        self.assertGreater(self.colour(flat(0, 0, 0), blacks=100)[0], 30)
        self.assertLess(self.colour(flat(20, 20, 20), blacks=-100)[0], 10)

    def test_the_tone_curve_moves_its_zones_alone(self):
        self.assertGreater(self.colour(flat(96, 96, 96), curve_darks=100)[0], 105)
        np.testing.assert_allclose(self.colour(flat(250, 250, 250), curve_darks=100), 250, atol=1)

    def test_the_mixer_changes_its_band_alone(self):
        self.assertLess(self.colour(flat(0, 0, 255), blue_luminance=-100)[2], 200)
        np.testing.assert_allclose(self.colour(flat(255, 0, 0), blue_luminance=-100), (255, 0, 0), atol=1)

    def test_vibrance_changes_the_muted_colours_most(self):
        muted = self.colour(flat(140, 120, 120), vibrance=100)
        vivid = self.colour(flat(255, 30, 30), vibrance=100)
        self.assertGreater(muted[0] - muted[1], 30)  # From 20.
        np.testing.assert_allclose(vivid, (255, 30, 30), atol=12)

    def test_the_shadows_and_the_highlights_change_their_areas(self):
        view = flat(30, 30, 30)
        view[:, VIEW[0] // 2:] = 230
        plain, lifted = self.draw(view), self.draw(view, shadows=100)
        self.assertGreater(lifted[plain == 30].mean(), 50)
        np.testing.assert_allclose(lifted[plain == 230].mean(), 230, atol=2)
        lowered = self.draw(view, highlights=-100)
        self.assertLess(lowered[plain == 230].mean(), 205)
        np.testing.assert_allclose(lowered[plain == 30].mean(), 30, atol=2)

    def test_sharpness_detail_and_structure_raise_the_contrast_of_edges(self):
        # An edge each 10 pixels, between two greys.
        view = flat(100, 100, 100)
        view[:, (np.arange(VIEW[0]) // 10) % 2 == 1] = 140
        plain = self.draw(view).std()
        for tool in ("sharpness", "detail", "structure"):
            self.assertGreater(self.draw(view, **{tool: 100}).std(), plain + 0.3, tool)
        self.assertLess(self.draw(view, detail=-100).std(), plain)

    def test_a_view_is_filtered_alone(self):
        # Black views beside white ones: nothing of one may reach the other, whatever the filter.
        quilt = quilt_of(flat(128, 128, 128))
        for row in range(6):
            for column in range(8):
                if (row + column) % 2:
                    quilt[row * 80:(row + 1) * 80, column * 60:(column + 1) * 60] = 40
        self.renderer.quilt(quilt, PORTRAIT, CALIBRATION)
        plain = self.renderer.read()
        self.renderer.quilt(quilt, PORTRAIT, CALIBRATION, grade=Grade.of({"sharpness": 150, "detail": 100,
                                                                         "structure": 100}))
        self.assertLessEqual(np.abs(self.renderer.read().astype(int) - plain).max(), 1)

    def test_a_black_sky_gets_no_bright_rim(self):
        view = flat(0, 0, 0)
        view[20:60, 20:40] = 100
        self.assertLess(self.draw(view, sharpness=100).max(), 150)

    def test_a_grade_switched_off_shows_the_quilt_as_it_is(self):
        np.testing.assert_array_equal(self.draw(ramps(), exposure=2, enabled=False), self.draw(ramps()))

    def test_another_grade_of_the_same_picture_keeps_what_it_can(self):
        quilt, grade = quilt_of(ramps()), Grade.of({"exposure": 1})
        self.renderer.quilt(quilt, PORTRAIT, CALIBRATION, grade=grade)
        kept = self.renderer.graded
        once = self.renderer.read()
        self.renderer.quilt(quilt, PORTRAIT, CALIBRATION, grade=Grade.of({"exposure": 1, "sharpness": 50}))
        self.assertIs(self.renderer.graded, kept)
        self.renderer.quilt(quilt, PORTRAIT, CALIBRATION, grade=grade)
        np.testing.assert_array_equal(self.renderer.read(), once)
        self.renderer.quilt(quilt.copy(), PORTRAIT, CALIBRATION, grade=grade)  # Another picture.
        self.assertIsNot(self.renderer.graded, kept)
        np.testing.assert_array_equal(self.renderer.read(), once)
        self.renderer.black()
        self.assertIsNone(self.renderer.graded)

    def test_the_whole_quilt_has_the_colours_of_its_hologram(self):
        quilt = np.random.default_rng(1).integers(0, 256, (6 * 80, 8 * 60, 3), dtype=np.uint8)
        grade = Grade.of({"exposure": 0.5, "shadows": 60, "sharpness": 80, "structure": 40, "blue_hue": 30})
        self.renderer.quilt(quilt, PORTRAIT, CALIBRATION, True, grade)
        hologram, kept = self.renderer.read(), self.renderer.graded
        saved = self.renderer.graded_picture(quilt, PORTRAIT, grade)
        self.assertEqual((saved.shape, saved.dtype), (quilt.shape, quilt.dtype))
        # What is shown is kept as it was.
        self.assertIs(self.renderer.graded, kept)
        self.renderer.quilt(quilt, PORTRAIT, CALIBRATION, True, grade)
        np.testing.assert_array_equal(self.renderer.read(), hologram)
        # The saved quilt, shown as it is, is the graded one.
        self.renderer.quilt(saved, PORTRAIT, CALIBRATION, True)
        np.testing.assert_array_equal(self.renderer.read(), hologram)

    def test_the_whole_quilt_stays_the_right_way_up(self):
        quilt = quilt_of(flat(10, 10, 10))
        quilt[:40, :30] = 200  # The top left.
        saved = self.renderer.graded_picture(quilt, PORTRAIT, Grade.of({"exposure": 0.2}))
        self.assertTrue((saved[:40, :30] > 100).all())
        self.assertTrue((saved[40:] < 100).all() and (saved[:, 30:] < 100).all())

    def test_what_is_shown_next_is_not_graded(self):
        plain = self.draw(ramps())
        self.draw(ramps(), exposure=2, sharpness=50)
        np.testing.assert_array_equal(self.draw(ramps()), plain)


if __name__ == "__main__":
    unittest.main()
