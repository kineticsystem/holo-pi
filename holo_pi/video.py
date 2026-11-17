"""Videos for a Looking Glass: read one, and play it on a screen in a loop.

There are two kinds. A quilt video is a video whose every frame is a quilt: the
GPU interleaves each frame as it is shown, see gl.py, or the processor, slowly,
without one. It plays on any Looking Glass of its layout.

A hologram video is a video whose every frame is a hologram, the image the
Looking Glass's screen shows, interleaved with its calibration beforehand, e.g.
the videos a Portrait keeps on its own drive and plays without a computer. The
server only shows its frames, pixel for pixel: it plays a video made for this
Looking Glass only. Its frames are the screen's size, e.g. 1536 x 2048 for a
Portrait, or twice as wide, as the Portrait's own videos are, e.g. 3072 x 2048:
each pixel of the screen is then two pixels of the video, which keeps its colour
whole through the encoding's 4:2:0, which stores one colour for two pixels side
by side. The player shows one pixel of each two.

Decoding needs PyAV, python3-av. The player decodes with the hardware decoder
when FFmpeg reaches one, e.g. the Raspberry Pi 5's for HEVC, with Raspberry Pi's
build of FFmpeg, and on the processor otherwise. On a Pi 5, a quilt video of
3360 x 3360 in HEVC at 49 Mbit/s decodes at about 43 frames a second with the
hardware decoder, with about one core to copy its frames out, and at about 11 on
the processor, with all four.
"""

import collections
import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)

# How long the player waits, after the screen fails, e.g. because the Looking Glass is switched off, to try again.
RETRY_S = 5
# The frames decoded ahead of the screen: enough to play on while the decoder starts the video again, about 0.4
# seconds on a Pi 5, at 30 frames a second. A Portrait's frame is 12.6 MB.
AHEAD = 16
# How far behind its time the player may fall, e.g. when decoding is slower than the frame rate, before it takes
# the frame it has as the new start.
RESYNC_S = 1


class VideoError(ValueError):
    """A video that cannot be played whatever the Looking Glass: not a video, or not a hologram of its size."""


class NoPyAV(RuntimeError):
    """No video can be played: PyAV is not installed."""


@dataclass
class VideoInfo:
    width: int
    height: int
    fps: Optional[float]  # Frames a second, if the file says.
    frames: Optional[int]  # The number of frames, if the file says.
    duration: Optional[float]  # In seconds, if the file says.
    codec: str  # e.g. hevc.


def _av():
    try:
        import av
    except ImportError as error:
        raise NoPyAV(f"playing a video needs PyAV, python3-av: {error}") from error
    return av


def open_video(av, path):
    """The video at `path`, opened to decode with the hardware decoder of DRM, the Raspberry Pi 5's for HEVC, when
    FFmpeg has one for its codec, and on the processor otherwise."""
    try:
        from av.codec.hwaccel import HWAccel
        return av.open(path, hwaccel=HWAccel(device_type="drm", allow_software_fallback=True))
    except (ImportError, av.error.FFmpegError, ValueError, TypeError):  # An older PyAV, or no DRM device.
        return av.open(path)


def probe(path, name=None):
    """What the video at `path` is, from its first video stream and its first frame. Raises VideoError if it is not
    a video. `name` names it in the error."""
    av = _av()
    name = name or str(path)
    try:
        with av.open(str(path)) as container:
            if not container.streams.video:
                raise VideoError(f"no video in {name}")
            stream = container.streams.video[0]
            first = next(container.decode(stream), None)
            if first is None:
                raise VideoError(f"no frame in the video {name}")
            fps = float(stream.average_rate or stream.guessed_rate or 0) or None
            duration = None
            if container.duration:
                duration = container.duration / av.time_base
            elif stream.duration and stream.time_base:
                duration = float(stream.duration * stream.time_base)
            frames = stream.frames or (round(duration * fps) if duration and fps else None)
            return VideoInfo(first.width, first.height, fps, frames, duration, stream.codec_context.name)
    except av.error.FFmpegError as error:
        raise VideoError(f"cannot read the video {name}: {error}") from error


def step(width, height, screen_width, screen_height):
    """The columns of the video per pixel of the screen: 1 for a video of the screen's size, 2 for one twice as
    wide. Raises VideoError for any other size."""
    if height == screen_height and width in (screen_width, 2 * screen_width):
        return width // screen_width
    raise VideoError(f"a video of {width} x {height} is not a hologram for a screen of {screen_width} x "
                     f"{screen_height}: its frames must be {screen_width} x {screen_height}, or "
                     f"{2 * screen_width} x {screen_height}, as a Portrait's own videos")


def hologram_pictures(step=1):
    """What the decoder makes of a hologram video's frame: the picture the screen shows, XRGB8888, one column of
    each `step`."""
    def picture(frame):
        # BGRA is XRGB8888 in memory, the screen's format: no conversion left to do.
        picture = frame.to_ndarray(format="bgra")
        if step > 1:
            # One column of each `step`, pixel by pixel rather than byte by byte: eight times faster.
            picture = np.ascontiguousarray(picture.view(np.uint32)[:, ::step]).view(np.uint8)
        return picture
    return picture


def yuv_frames(frame):
    """What the decoder makes of a quilt video's frame for the GPU: the frame itself, YUV 4:2:0."""
    return frame if frame.format.name == "yuv420p" else frame.reformat(format="yuv420p")


class Player:
    """Plays a video in a loop, at its frame rate, until stop(): `convert` makes each frame ready, on the decoder's
    thread, e.g. hologram_pictures(); `show` puts it on the screen, on the player's, and returns where. With
    `then`, (path, show, convert) of a second video, it plays the first once, then the second in a loop, with no
    gap between them: the decoder goes on into the second while the first is still shown. segment says which is
    on the screen, 0 or 1.

    Two threads: the decoder decodes the frames ahead, again and again, into a queue of AHEAD frames, so that
    starting the video again, when its decoder fills up anew, does not stop the screen; the player shows each
    frame when its time comes, and skips the frames it is too late for, to keep time. When the screen fails, e.g.
    because the Looking Glass is switched off, it tries again every RETRY_S. shown_on says where the video is shown
    and error why not; started is set once the first frame is shown, or cannot be."""

    def __init__(self, path, show, convert=None, then=None):
        # The videos to play: (path, show, convert), the last in a loop, those before it once.
        self.segments = [(str(path), show, convert or hologram_pictures())]
        if then is not None:
            then_path, then_show, then_convert = then
            self.segments.append((str(then_path), then_show, then_convert or hologram_pictures()))
        self.segment = 0  # The one on the screen.
        self.shown_on = None
        self.error = None
        self.shown_at = collections.deque(maxlen=49)  # When the last frames were shown, for frame_rate().
        self.decoding = None  # "hardware" or "software", once the first frame is decoded.
        self.started = threading.Event()
        self.stopping = threading.Event()
        self.frames = queue.Queue(AHEAD)  # (when, period, picture, segment), or the VideoError that ends it.
        self.thread = threading.Thread(target=self._run, name="video", daemon=True)
        self.decoder = threading.Thread(target=self._decode, name="video decoder", daemon=True)

    def start(self):
        self.decoder.start()
        self.thread.start()
        return self

    def stop(self, timeout=5):
        self.stopping.set()
        for thread in (self.thread, self.decoder):
            if thread.is_alive() and thread is not threading.current_thread():
                thread.join(timeout)

    # The decoder.

    def _decode(self):
        av = _av()
        offset = 0.0  # When this round starts, in seconds from the start of the first.
        segment = 0
        try:
            while not self.stopping.is_set():
                path, _, convert = self.segments[segment]
                with open_video(av, path) as container:
                    stream = container.streams.video[0]
                    stream.thread_type = "AUTO"  # On the processor, decoding on every core.
                    period = 1 / float(stream.average_rate or stream.guessed_rate or 24)
                    first, length = None, 0.0
                    for number, frame in enumerate(container.decode(stream)):
                        if self.decoding is None:
                            self.decoding = "hardware" if getattr(stream.codec_context, "is_hwaccel", False) \
                                else "software"
                            log.info("Decoding the video with the %s decoder", self.decoding)
                        at = frame.time if frame.time is not None else number * period
                        first = at if first is None else first
                        length = at - first + period
                        if not self._put((offset + at - first, period, convert(frame), segment)):
                            return
                    if first is None:
                        raise VideoError("no frame in the video")
                offset += length
                segment = min(segment + 1, len(self.segments) - 1)   # The last one, again and again.
        except (av.error.FFmpegError, ValueError) as error:  # The file: playing it again would fail again.
            self._put(VideoError(f"cannot play the video: {error}"))

    def _put(self, item):
        """Queues `item` once there is room. Returns False if the player stops first."""
        while not self.stopping.is_set():
            try:
                self.frames.put(item, timeout=0.1)
                return True
            except queue.Full:
                pass
        return False

    # The player.

    def _run(self):
        origin = None  # When the first frame of the first round is due.
        shown = float("-inf")  # When the last frame was shown.
        while not self.stopping.is_set():
            try:
                item = self.frames.get(timeout=0.1)
            except queue.Empty:
                continue
            if isinstance(item, VideoError):
                self._failed(str(item))
                return
            at, period, picture, segment = item
            now = time.monotonic()
            if origin is None or now - (origin + at) > RESYNC_S:
                origin = now - at  # The first frame, or far behind, e.g. decoding slower than the frame rate.
            late = now - (origin + at)
            if late < 0:
                if self.stopping.wait(-late):
                    return
            elif late > period and now - shown < period:
                # Too late for this one, and the screen has just had one: the next one keeps time. When decoding
                # is what is slow, every frame is shown, later than its time.
                continue
            try:
                self._show(picture, segment)
            except ValueError as error:  # The video, e.g. a quilt larger than the GPU takes: it would fail again.
                self._failed(f"cannot play the video: {error}")
                return
            except RuntimeError as error:  # The screen.
                self._failed(str(error))
                origin = None
                if self.stopping.wait(RETRY_S):
                    return
                continue
            shown = time.monotonic()

    def _show(self, picture, segment=0):
        where = self.segments[segment][1](picture)
        self.segment = segment
        if self.shown_on is None:
            log.info("Playing the video on %s", where)
        self.shown_on, self.error = where, None
        self.shown_at.append(time.monotonic())
        self.started.set()

    def frame_rate(self):
        """The frames shown a second, over the last two seconds or so; None before two frames, or when stopped."""
        times = list(self.shown_at)
        if len(times) < 2 or time.monotonic() - times[-1] > 1:
            return None
        return (len(times) - 1) / (times[-1] - times[0])

    def _failed(self, error):
        if error != self.error:
            log.warning("Cannot show the video yet: %s", error)
        self.shown_on, self.error = None, error
        self.started.set()
