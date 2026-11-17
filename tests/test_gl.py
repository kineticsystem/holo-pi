"""Tests the GPU's interleaving, off screen, against the processor's: skipped without EGL and OpenGL ES 3."""

import unittest

import numpy as np

from holo_pi import Interleaver, Layout, load_calibration, numbers_quilt
from test_holo_pi import PORTRAIT, VISUAL, numbered_quilt

try:
    from holo_pi.gl import Offscreen
    CALIBRATION = load_calibration(VISUAL)
    OFFSCREEN = Offscreen(CALIBRATION.width, CALIBRATION.height)
except (OSError, RuntimeError) as error:  # No GPU, or no EGL: e.g. a computer without a graphics driver.
    raise unittest.SkipTest(f"no OpenGL ES 3 off screen: {error}")

try:
    import av
except ImportError:
    av = None


def interleaved(quilt, layout=PORTRAIT, reverse=False):
    return Interleaver(CALIBRATION, layout, quilt.shape[1], quilt.shape[0], reverse, cache=False)(quilt)


class GlTest(unittest.TestCase):
    renderer = OFFSCREEN.renderer

    def assert_close(self, gpu, cpu, levels, share):
        difference = np.abs(gpu.astype(int) - cpu)
        self.assertGreaterEqual((difference <= levels).mean(), share)

    def test_interleaves_a_quilt_as_the_processor(self):
        quilt = numbered_quilt()
        self.renderer.quilt(quilt, PORTRAIT, CALIBRATION)
        # The same view for each sub-pixel, but a few at the edge between two views, where the GPU's 32-bit floats
        # round otherwise than numpy's 64-bit ones.
        self.assert_close(self.renderer.read(), interleaved(quilt), 0, 0.999)

    def test_reverses_the_views(self):
        quilt = numbered_quilt()
        self.renderer.quilt(quilt, PORTRAIT, CALIBRATION, reverse=True)
        self.assert_close(self.renderer.read(), interleaved(quilt, reverse=True), 0, 0.999)

    def test_takes_another_layout(self):
        layout = Layout(5, 9)
        quilt = numbered_quilt(layout, 30, 40)
        self.renderer.quilt(quilt, layout, CALIBRATION)
        self.assert_close(self.renderer.read(), interleaved(quilt, layout), 0, 0.999)

    @unittest.skipIf(av is None, "no PyAV")
    def test_interleaves_a_video_frame_in_yuv(self):
        quilt = numbers_quilt()  # Colours: the conversion from YUV matters.
        frame = av.VideoFrame.from_ndarray(quilt, format="rgb24").reformat(format="yuv420p")
        self.renderer.quilt_frame(frame, PORTRAIT, CALIBRATION)
        # FFmpeg's own conversion back to RGB blends the colour of neighbouring pixels; the GPU takes the nearest.
        self.assert_close(self.renderer.read(), interleaved(frame.to_ndarray(format="rgb24")), 4, 0.97)

    def test_shows_a_hologram_as_it_is(self):
        rng = np.random.default_rng(1)
        hologram = rng.integers(0, 256, (CALIBRATION.height, CALIBRATION.width, 3), dtype=np.uint8)
        self.renderer.hologram(hologram)
        np.testing.assert_array_equal(self.renderer.read(), hologram)
        bgrx = np.concatenate([hologram[..., ::-1], np.full(hologram.shape[:2] + (1,), 255, np.uint8)], -1)
        self.renderer.hologram(bgrx)
        np.testing.assert_array_equal(self.renderer.read(), hologram)

    def test_refuses_a_quilt_larger_than_the_gpu_takes(self):
        side = self.renderer.largest + 8
        with self.assertRaisesRegex(ValueError, "larger than the GPU takes"):
            self.renderer.quilt(np.zeros((8, side, 3), np.uint8), PORTRAIT, CALIBRATION)

    def test_black(self):
        self.renderer.black()
        self.assertEqual(int(self.renderer.read().max()), 0)


if __name__ == "__main__":
    unittest.main()
