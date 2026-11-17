"""Tests reading hologram videos and playing them in a loop, with a fake screen: skipped without PyAV."""

import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

try:
    import av  # noqa: F401
except ImportError as error:  # PyAV is optional.
    raise unittest.SkipTest(f"no PyAV: {error}")

from holo_pi.video import Player, VideoError, hologram_pictures, probe, step

# Each frame's colour, as blue, green, red: what the screen gets, XRGB8888 in memory.
COLOURS = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]


def hologram_video(path, width, height, colours=COLOURS, fps=24, doubled=False):
    """Writes a lossless video, FFV1, whose frame n is filled with colours[n], as blue, green, red. Doubled, it is
    twice as wide, as a Portrait's own videos, and the second pixel of each two is black: the player must not
    show it."""
    with av.open(str(path), "w") as container:
        stream = container.add_stream("ffv1", rate=fps)
        stream.width, stream.height, stream.pix_fmt = width * (2 if doubled else 1), height, "bgr0"
        for blue, green, red in colours:
            frame = np.zeros((height, stream.width, 3), np.uint8)
            frame[:, ::2 if doubled else 1] = (red, green, blue)
            for packet in stream.encode(av.VideoFrame.from_ndarray(frame, format="rgb24")):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return path


def quilt_video(path, quilt, frames=4, fps=24):
    """Writes a lossless video, FFV1, whose every frame is `quilt`, an RGB array."""
    with av.open(str(path), "w") as container:
        stream = container.add_stream("ffv1", rate=fps)
        stream.width, stream.height, stream.pix_fmt = quilt.shape[1], quilt.shape[0], "bgr0"
        for _ in range(frames):
            for packet in stream.encode(av.VideoFrame.from_ndarray(quilt, format="rgb24")):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return path


class RecordingScreen:
    """A screen that keeps the colour of every frame it is shown, and how many, or is switched off."""

    name = "fake"

    def __init__(self):
        self.colours = []
        self.shape = None
        self.on = True
        self.lock = threading.Lock()

    def show(self, hologram):
        if not self.on:
            raise RuntimeError("no screen of 1536 x 2048")
        colours = np.unique(hologram.reshape(-1, hologram.shape[-1]), axis=0)
        with self.lock:
            self.shape = hologram.shape
            self.colours.append(tuple(int(c) for c in colours[0][:3]) if len(colours) == 1 else "mixed")
        return "the fake screen"

    def wait_for(self, count, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self.lock:
                if len(self.colours) >= count:
                    return list(self.colours)
            time.sleep(0.01)
        raise AssertionError(f"only {len(self.colours)} frames shown, not {count}")


class SlowAv:
    """PyAV, whose containers take `delay` seconds to decode each frame, and `opening` seconds to open."""

    def __init__(self, delay=0, opening=0):
        self.delay = delay
        self.opening = opening

    def __getattr__(self, name):
        return getattr(av, name)

    def open(self, *arguments, **options):
        time.sleep(self.opening)
        container, delay = av.open(*arguments, **options), self.delay

        class Slow:
            streams = container.streams

            def __enter__(self):
                return self

            def __exit__(self, *_):
                container.close()

            def decode(self, stream):
                for frame in container.decode(stream):
                    time.sleep(delay)
                    yield frame

        return Slow()


class VideoTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name)

    def tearDown(self):
        self.folder.cleanup()

    def test_reads_what_the_video_is(self):
        info = probe(hologram_video(self.path / "test.mkv", 64, 16, doubled=True))
        self.assertEqual((info.width, info.height, info.fps, info.codec), (128, 16, 24.0, "ffv1"))

    def test_refuses_what_is_not_a_video(self):
        path = self.path / "test.mp4"
        path.write_bytes(b"not a video")
        with self.assertRaisesRegex(VideoError, "cannot read the video test.mp4"):
            probe(path, "test.mp4")

    def test_a_video_is_the_screens_size_or_twice_as_wide(self):
        self.assertEqual(step(1536, 2048, 1536, 2048), 1)
        self.assertEqual(step(3072, 2048, 1536, 2048), 2)
        with self.assertRaisesRegex(VideoError, "must be 1536 x 2048, or 3072 x 2048"):
            step(3360, 3360, 1536, 2048)

    def test_plays_every_frame_in_order_and_again(self):
        screen = RecordingScreen()
        path = hologram_video(self.path / "test.mkv", 64, 16, doubled=True)
        player = Player(path, screen.show, hologram_pictures(2)).start()
        try:
            shown = screen.wait_for(10)
        finally:
            player.stop()
        # One pixel of each two: never the black one, never a mix.
        self.assertEqual(shown[:10], (COLOURS * 3)[:10])
        self.assertEqual(screen.shape, (16, 64, 4))
        self.assertEqual(player.shown_on, "the fake screen")
        self.assertFalse(player.thread.is_alive() or player.decoder.is_alive())

    def test_keeps_the_frame_rate(self):
        screen = RecordingScreen()
        player = Player(hologram_video(self.path / "test.mkv", 64, 16, fps=50), screen.show).start()
        try:
            start = time.monotonic()
            screen.wait_for(1)
            screen.wait_for(11)
            elapsed = time.monotonic() - start
        finally:
            player.stop()
        # 10 frames after the first, at 50 a second: 0.2 seconds.
        self.assertGreater(elapsed, 0.18)
        self.assertLess(elapsed, 0.6)

    def test_keeps_playing_when_decoding_is_slower_than_the_frame_rate(self):
        screen = RecordingScreen()
        with mock.patch("holo_pi.video._av", lambda: SlowAv(0.05)):  # 20 frames a second, of 50.
            player = Player(hologram_video(self.path / "test.mkv", 64, 16, fps=50), screen.show).start()
            try:
                shown = screen.wait_for(6, timeout=3)
            finally:
                player.stop()
        # It skips the frames it is late for, but never stops showing.
        self.assertGreater(len(set(shown)), 1)

    def test_plays_on_while_the_video_starts_again(self):
        screen, times = RecordingScreen(), []
        show = screen.show
        screen.show = lambda hologram: (times.append(time.monotonic()), show(hologram))[1]
        colours = [(8 * n, 0, 0) for n in range(30)]  # 0.6 seconds at 50 frames a second.
        path = hologram_video(self.path / "test.mkv", 64, 16, colours, fps=50)
        with mock.patch("holo_pi.video._av", lambda: SlowAv(opening=0.15)):
            player = Player(path, screen.show).start()
            try:
                screen.wait_for(90, timeout=5)  # Three rounds.
            finally:
                player.stop()
        # Past the first round, the frames decoded ahead cover the 0.15 seconds each start takes.
        gaps = [later - earlier for earlier, later in zip(times[30:], times[31:90])]
        self.assertLess(max(gaps), 0.1)

    def test_tries_again_when_the_screen_comes_back(self):
        screen = RecordingScreen()
        screen.on = False
        with mock.patch("holo_pi.video.RETRY_S", 0.05):
            player = Player(hologram_video(self.path / "test.mkv", 64, 16), screen.show).start()
            try:
                self.assertTrue(player.started.wait(5))
                self.assertEqual((player.shown_on, player.error), (None, "no screen of 1536 x 2048"))
                screen.on = True
                screen.wait_for(1)
                self.assertIsNone(player.error)
            finally:
                player.stop()

    def test_a_broken_video_stops_the_player(self):
        path = self.path / "test.mp4"
        path.write_bytes(b"not a video")
        player = Player(path, RecordingScreen().show).start()
        self.assertTrue(player.started.wait(5))
        player.thread.join(5)
        player.decoder.join(5)
        self.assertFalse(player.thread.is_alive() or player.decoder.is_alive())
        self.assertIn("cannot play the video", player.error)


if __name__ == "__main__":
    unittest.main()
