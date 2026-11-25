"""Tests the transitions, off screen, between holograms drawn by the GPU: skipped without EGL and OpenGL ES 3."""

import queue
import threading
import unittest
from unittest import mock

import numpy as np

from holo_pi.grade import Grade
from holo_pi.transition import CUT, KINDS
from test_holo_pi import PORTRAIT, numbered_quilt

try:
    from test_gl import CALIBRATION, OFFSCREEN, av  # The same: a second context would take the place of the first.

    from holo_pi.gl import GlScreen
except unittest.SkipTest as skipped:
    raise unittest.SkipTest(str(skipped))

SIZE = (CALIBRATION.height, CALIBRATION.width, 3)
A, B = np.full(SIZE, 200, np.uint8), np.full(SIZE, 40, np.uint8)
MOVING = [kind for kind in KINDS if kind != CUT]


class TransitionTest(unittest.TestCase):
    renderer = OFFSCREEN.renderer

    def setUp(self):
        self.now = 100.0
        patch = mock.patch.object(self.renderer, "clock", lambda: self.now)
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(self.renderer.black)
        self.renderer.hologram(A)

    def at(self, seconds):
        self.now = 100.0 + seconds
        self.renderer.step()
        return self.renderer.read()

    def test_starts_with_the_one_and_ends_with_the_other(self):
        for kind in MOVING:
            with self.subTest(kind):
                self.now = 100.0
                self.renderer.hologram(A)
                self.renderer.transition(kind, 2)
                self.renderer.hologram(B)
                np.testing.assert_array_equal(self.renderer.read(), A)
                self.assertTrue(self.renderer.moving)
                middle = self.at(1)
                self.assertFalse((middle == A).all() or (middle == B).all())
                np.testing.assert_array_equal(self.at(2), B)
                self.assertFalse(self.renderer.moving)

    def test_a_cross_fade_is_half_of_each_in_the_middle(self):
        self.renderer.transition("cross fade", 2)
        self.renderer.hologram(B)
        np.testing.assert_allclose(self.at(1).astype(int), 120, atol=1)

    def test_through_black_is_black_in_the_middle(self):
        self.renderer.transition("fade through black", 2)
        self.renderer.hologram(B)
        self.assertLessEqual(int(self.at(1).max()), 1)

    def test_through_white_is_white_in_the_middle(self):
        self.renderer.transition("fade through white", 2)
        self.renderer.hologram(B)
        self.assertGreaterEqual(int(self.at(1).min()), 254)

    def test_blends_each_sub_pixel_of_two_quilts_with_the_same_view(self):
        self.renderer.quilt(numbered_quilt(), PORTRAIT, CALIBRATION)
        before = self.renderer.read().astype(int)
        self.renderer.transition("cross fade", 2)
        other = 255 - numbered_quilt()
        self.renderer.quilt(other, PORTRAIT, CALIBRATION)
        middle = self.at(1).astype(int)
        after = self.at(2).astype(int)
        np.testing.assert_allclose(middle, (before + after) / 2, atol=1)
        self.renderer.quilt(other, PORTRAIT, CALIBRATION)
        np.testing.assert_array_equal(self.renderer.read(), after)

    def test_a_graded_quilt_goes_into_another_and_back(self):
        quilt = numbered_quilt() * 2
        grade = Grade.of({"exposure": 1})
        self.renderer.quilt(quilt, PORTRAIT, CALIBRATION, grade=grade)
        graded = self.renderer.read()
        self.renderer.transition("cross fade", 2)
        self.renderer.hologram(B)  # Gives the graded quilt's memory back.
        np.testing.assert_array_equal(self.renderer.read(), graded)
        np.testing.assert_array_equal(self.at(2), B)
        self.now = 100.0
        self.renderer.transition("cross fade", 2)
        self.renderer.quilt(quilt, PORTRAIT, CALIBRATION, grade=grade)
        np.testing.assert_array_equal(self.renderer.read(), B)
        np.testing.assert_array_equal(self.at(2), graded)

    def test_a_grade_changed_meanwhile_goes_into_it(self):
        quilt = numbered_quilt() * 2
        self.renderer.quilt(quilt, PORTRAIT, CALIBRATION, grade=Grade.of({"exposure": 1}))
        wanted = self.renderer.read()
        self.renderer.hologram(A)
        self.renderer.transition("cross fade", 2)
        self.renderer.quilt(quilt, PORTRAIT, CALIBRATION)
        self.now += 1
        self.renderer.quilt(quilt, PORTRAIT, CALIBRATION, grade=Grade.of({"exposure": 1}))
        np.testing.assert_array_equal(self.at(2), wanted)

    @unittest.skipIf(av is None, "no PyAV")
    def test_a_video_plays_in_it_and_leaves_from_its_last_frame(self):
        def frame(value):
            picture = np.full((336, 336, 3), value, np.uint8)
            return av.VideoFrame.from_ndarray(picture, format="rgb24").reformat(format="yuv420p")

        def shown(value):
            self.renderer.quilt_frame(frame(value), PORTRAIT, CALIBRATION)
            return self.renderer.read()
        grey, white = shown(90), shown(220)
        self.renderer.hologram(A)
        self.renderer.transition("cross fade", 2)
        shown(90)
        self.now = 101.0
        np.testing.assert_allclose(shown(220).astype(int), (A.astype(int) + white) / 2, atol=1)
        np.testing.assert_array_equal(self.at(2), white)
        np.testing.assert_array_equal(shown(90), grey)  # Over: straight to the screen.
        self.renderer.transition("cross fade", 2)
        self.renderer.hologram(B)
        np.testing.assert_array_equal(self.renderer.read(), grey)

    @unittest.skipIf(av is None, "no PyAV")
    def test_a_first_frame_after_a_graded_quilt_has_its_colours(self):
        picture = np.full((336, 336, 3), 90, np.uint8)
        frame = av.VideoFrame.from_ndarray(picture, format="rgb24").reformat(format="yuv420p")
        self.renderer.quilt_frame(frame, PORTRAIT, CALIBRATION)
        wanted = self.renderer.read()
        self.renderer.quilt(numbered_quilt(), PORTRAIT, CALIBRATION, grade=Grade.of({"exposure": 1}))
        self.renderer.quilt_frame(frame, PORTRAIT, CALIBRATION)
        np.testing.assert_array_equal(self.renderer.read(), wanted)

    def test_another_transition_leaves_from_the_one_under_way(self):
        self.renderer.transition("cross fade", 2)
        self.renderer.hologram(B)
        middle = self.at(1)
        self.renderer.transition("fade through white", 2)
        self.renderer.hologram(A)
        np.testing.assert_array_equal(self.renderer.read(), middle)
        np.testing.assert_array_equal(self.at(4), A)

    def test_a_cut_and_black_end_it(self):
        self.renderer.transition("cross fade", 2)
        self.renderer.hologram(B)
        self.renderer.transition(CUT, 2)
        self.renderer.hologram(A)
        np.testing.assert_array_equal(self.renderer.read(), A)
        self.renderer.transition("cross fade", 2)
        self.renderer.hologram(B)
        self.renderer.black()
        self.assertEqual((int(self.renderer.read().max()), self.renderer.moving), (0, False))

    def test_leaves_from_black_too(self):
        self.renderer.black()
        self.renderer.transition("cross fade", 2)
        self.renderer.hologram(B)
        self.assertEqual(int(self.renderer.read().max()), 0)
        np.testing.assert_allclose(self.at(1).astype(int), 20, atol=1)

    def test_a_refused_quilt_after_a_graded_one_leaves_something_to_leave_from(self):
        self.renderer.quilt(numbered_quilt(), PORTRAIT, CALIBRATION, grade=Grade.of({"exposure": 1}))
        self.renderer.transition("cross fade", 2)
        with self.assertRaises(ValueError):
            self.renderer.quilt(np.zeros((8, self.renderer.largest + 8, 3), np.uint8), PORTRAIT, CALIBRATION)
        self.renderer.transition("cross fade", 2)
        self.renderer.hologram(B)
        np.testing.assert_array_equal(self.at(2), B)


class ScreenTest(unittest.TestCase):
    """GlScreen's thread, with a renderer and page flips of its own making."""

    class Renderer:
        def __init__(self, steps, failing=False):
            self.left, self.failing = steps, failing

        @property
        def moving(self):
            return self.left > 0

        def step(self):
            if self.failing:
                raise OSError("no page flip")
            self.left -= 1

    def screen(self, renderer):
        screen = GlScreen()
        screen.flips = []
        screen._flip = lambda: screen.flips.append(threading.current_thread().name)
        screen._call(lambda: setattr(screen, "renderer", renderer))
        return screen

    def test_draws_a_transition_on_by_itself(self):
        screen = self.screen(self.Renderer(5))
        for _ in range(100):
            if len(screen.flips) == 5:
                break
            threading.Event().wait(0.01)
        self.assertEqual(screen.flips, ["gl"] * 5)
        self.assertRaises(queue.Empty, screen.jobs.get_nowait)

    def test_takes_what_is_asked_meanwhile(self):
        screen = self.screen(self.Renderer(10**9))
        self.assertEqual(screen._call(lambda: 7), 7)
        screen._call(lambda: setattr(screen, "renderer", None))

    def test_a_step_that_fails_shows_the_picture_and_goes_on(self):
        shown = threading.Event()
        with self.assertLogs("holo_pi.gl", "WARNING"):
            screen = GlScreen()
            screen._release = lambda: setattr(screen, "renderer", None)
            screen._present = lambda *last: shown.set()
            screen.last = (1, 1, None)
            screen._call(lambda: setattr(screen, "renderer", self.Renderer(5, failing=True)))
            self.assertTrue(shown.wait(5))
        self.assertEqual(screen._call(lambda: 7), 7)


if __name__ == "__main__":
    unittest.main()
