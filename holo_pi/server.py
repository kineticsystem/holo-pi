"""The HTTP server: any computer on the network shows a quilt on the Looking Glass, or plays a video on it, by
uploading it.

`holo-pi serve` runs it: FastAPI, served by uvicorn on a thread of its own,
while the main thread runs the screen, GTK's loop on a desktop. Display holds
what is shown: it reads the calibration once it is there, keeps the table of
the last layouts in memory, and keeps the last quilt on disk, to show it again
after a restart. A quilt that cannot be shown yet, e.g. because the Looking
Glass is switched off, is kept, and shown as soon as it can be. A video, already
interleaved for this Looking Glass, plays in a loop on a thread of its own, the
Player's, until a quilt or another video replaces it; it is kept as a quilt is.

See docs/API.md for the API, and http://<host>:8095/docs for the same, live.
"""

import json
import logging
import os
import tempfile
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi import Path as FastApiPath
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__
from .calibration import find_calibration, load_calibration, mount_drives
from .interleave import Interleaver
from .layout import Layout
from .library import HOLOGRAM_VIDEO, QUILT, QUILT_VIDEO, Library, QuiltError
from .numbers import numbers_quilt
from .quilt import read_quilt
from .screen import open_screen
from .video import NoPyAV, Player, VideoError, hologram_pictures, step, yuv_frames

log = logging.getLogger(__name__)

# How often a quilt that could not be shown is tried again.
RETRY_S = 5
# The tables kept in memory, about 38 MB each for a Portrait: one per layout and size of quilt.
TABLES = 2
NUMBERS = "numbers"
KEPT = "The quilt is kept, and shown as soon as it can be."
SHOWN = "shown.json"  # What was shown last, in the state folder.
# Where what the Looking Glass shows comes from: the library, the test pattern, or the default quilt.
MEDIA, TEST_PATTERN, DEFAULT = "media", "test pattern", "default"
# How long an upload waits for the video's first frame on the screen, before it answers.
STARTED_S = 10
# The codec that a Raspberry Pi 5's hardware decoder decodes.
HARDWARE_CODEC = "hevc"


def codec_warning(codec):
    """What to say about a video of `codec`: None for H.265, which the Pi 5's hardware decoder decodes."""
    if codec == HARDWARE_CODEC:
        return None
    return (f"The video is {codec}, not H.265 (HEVC): a Raspberry Pi 5 decodes it on its processor, which may be too "
            "slow for a large quilt video, which then plays in slow motion. Encode it in H.265, which the Pi 5's "
            "hardware decoder decodes, e.g. ffmpeg -i <video> -c:v libx265 -crf 20 -pix_fmt yuv420p -tag:v hvc1 "
            "<new video>.")


def state_folder():
    base = os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state"
    return Path(base) / "holo-pi"


@dataclass
class Quilt:
    name: str  # As uploaded, e.g. helix_qs8x6a0.75.jpg, or "numbers" for the test quilt.
    columns: int
    rows: int
    reverse: bool
    width: int
    height: int
    uploaded: str  # UTC, ISO 8601.
    file: Optional[str]  # Its file in the library; None for the test quilt, which is drawn again, and the default.
    id: Optional[str] = None  # Its id in the library; None for the test quilt and the default.


@dataclass
class Video:
    name: str  # As uploaded, e.g. Anna.jpg__lkgrec.mp4.
    width: int
    height: int
    fps: Optional[float]
    frames: Optional[int]
    duration: Optional[float]  # In seconds.
    codec: str
    uploaded: str  # UTC, ISO 8601.
    file: str  # Its file in the library.
    # A quilt video's layout, and the order of its views; None for a hologram video, interleaved already.
    columns: Optional[int] = None
    rows: Optional[int] = None
    reverse: bool = False
    id: Optional[str] = None  # Its id in the library.


class Display:
    """What the Looking Glass shows, a quilt or a video, the library it takes them from, and the calibration it shows
    them with. Thread-safe."""

    def __init__(self, screen, calibration=None, state=None, mount=False, default=None):
        self.screen = screen
        self.calibration_path = calibration
        self.state = Path(state) if state else None
        # What to show when nothing is kept, e.g. at the first start: "numbers", or the path of a quilt.
        self.default = default
        # Without a desktop, nothing mounts the Looking Glass's drive: with `mount`, the server mounts it itself,
        # which needs root, e.g. in its container.
        self.mount = mount
        self.lock = threading.RLock()
        self._calibration = None
        self.calibration_error = None
        self.tables = {}
        self.quilt = None
        self.picture = None
        self.shown_on = None
        self.error = None
        # A video, in place of the quilt: the player plays it once it can, and says where, or why not.
        self.video = None
        self.player = None
        self.video_error = None  # Why the video has no player, e.g. no calibration yet.
        self.scratch = None if self.state else tempfile.TemporaryDirectory(prefix="holo-pi-")
        self.library = Library(self._folder() / "library")
        self.stopping = threading.Event()

    def _folder(self):
        """The state folder, or a temporary one without it."""
        return self.state if self.state is not None else Path(self.scratch.name)

    # The calibration.

    def calibration(self):
        """The Looking Glass's calibration, read once. Raises RuntimeError if it is not there yet."""
        with self.lock:
            if self._calibration is None:
                try:
                    self._calibration = self._read_calibration()
                    self.calibration_error = None
                    log.info("The calibration of %s, %d x %d", self._calibration.serial, self._calibration.width,
                             self._calibration.height)
                except RuntimeError as error:
                    self.calibration_error = str(error)
                    raise
            return self._calibration

    def _read_calibration(self):
        if self.calibration_path:
            return load_calibration(self.calibration_path)
        try:
            return find_calibration()
        except RuntimeError:
            if not self.mount or not mount_drives():
                raise
            return find_calibration()

    def _screen_size(self):
        try:
            calibration = self.calibration()
        except RuntimeError:
            return None  # Checked when it is there.
        return calibration.width, calibration.height

    def _interleaver(self, calibration, layout, width, height, reverse):
        key = (calibration, layout, width, height, reverse)
        interleaver = self.tables.pop(key, None) or Interleaver(calibration, layout, width, height, reverse)
        self.tables[key] = interleaver  # The most recent last.
        while len(self.tables) > TABLES:
            self.tables.pop(next(iter(self.tables)))
        return interleaver

    # The library.

    def store(self, source, name, columns=None, rows=None, reverse=False):
        """Keeps the upload in `source`, a binary file, in the library, without showing it. Returns its Item. Raises
        QuiltError or VideoError if it cannot be shown whatever the Looking Glass."""
        return self.library.add(source, name, columns, rows, reverse, self._screen_size())

    def play(self, id=None, name=None):
        """Shows the library's quilt, or plays its video, of this id, or else of this name. Returns where. Raises
        KeyError if there is none, and RuntimeError if it cannot be shown yet: it is kept, and shown as soon as it
        can be."""
        item = self.library.find(id, name)
        if item is None:
            raise KeyError(f"no quilt or video of the {'id' if id is not None else 'name'} {id or name!r}")
        return self.play_item(item)

    def play_item(self, item, picture=None):
        """Shows a library's item; `picture`, a quilt's, if it is read already."""
        path = self.library.path(item)
        if item.is_video:
            with self.lock:
                self._drop_video()
                self.quilt, self.picture, self.shown_on, self.error = None, None, None, None
                self.video = Video(item.name, item.width, item.height, item.fps, item.frames, item.duration,
                                   item.codec, item.uploaded, str(path), item.columns, item.rows, item.reverse, item.id)
                self._keep({"id": item.id})
                return self._play()
        if picture is None:
            try:
                picture = read_quilt(path, item.name)
            except RuntimeError as error:
                raise QuiltError(str(error)) from error
        with self.lock:
            self._set(Quilt(item.name, item.columns, item.rows, item.reverse, item.width, item.height, item.uploaded,
                            str(path), item.id), picture, {"id": item.id})
            return self._show()

    def shown_id(self):
        """The library's id of what is shown, or None."""
        with self.lock:
            return (self.video or self.quilt).id if (self.video or self.quilt) else None

    def remove(self, item):
        """Removes an item from the library; if it is shown, shows black."""
        with self.lock:
            if self.shown_id() == item.id:
                self.clear()
            self.library.remove(item)

    def remove_all(self):
        """Empties the library; shows black if what is shown came from it."""
        with self.lock:
            if self.shown_id() is not None:
                self.clear()
            for item in self.library.list():
                self.library.remove(item)

    # What is shown.

    def show_test_pattern(self, reverse=False):
        """Shows the test pattern: the test quilt of numbered views."""
        picture = numbers_quilt()
        with self.lock:
            self._set(Quilt(NUMBERS, 8, 6, reverse, picture.shape[1], picture.shape[0], _now(), None), picture,
                      {"numbers": True, "reverse": reverse})
            return self._show()

    def clear(self):
        """Shows black: what was shown stays in the library."""
        with self.lock:
            self._drop_video()
            self.quilt, self.picture, self.shown_on, self.error = None, None, None, None
            self._forget()
            self.screen.clear()

    def _set(self, quilt, picture, kept=None):
        self._drop_video()
        self.quilt, self.picture, self.shown_on, self.error = quilt, picture, None, None
        if kept is not None:
            self._keep(kept)

    def _show(self):
        quilt = self.quilt
        try:
            calibration = self.calibration()
            layout = Layout(quilt.columns, quilt.rows)
            if hasattr(self.screen, "show_quilt"):  # The GPU interleaves it.
                self.shown_on = self.screen.show_quilt(self.picture, layout, calibration, quilt.reverse)
            else:
                hologram = self._interleaver(calibration, layout, quilt.width, quilt.height, quilt.reverse)
                self.shown_on = self.screen.show(hologram(self.picture))
            self.error = None
            log.info("Showing %s on %s", quilt.name, self.shown_on)
            return self.shown_on
        except RuntimeError as error:
            if str(error) != self.error:
                log.warning("Cannot show %s yet: %s", quilt.name, error)
            self.error = str(error)
            raise

    # The video.

    def _play(self):
        """Starts the player of the video, and waits for its first frame. Returns where it is shown; raises
        RuntimeError if it cannot be, yet: when the player has the error, it tries again by itself."""
        video = self.video
        try:
            calibration = self.calibration()
            if video.columns is None:  # A hologram video: its frames as they are.
                show, convert = self.screen.show, hologram_pictures(
                    step(video.width, video.height, calibration.width, calibration.height))
            else:
                show, convert = self._quilt_player(video, calibration)
        except (RuntimeError, VideoError) as error:
            if str(error) != self.video_error:
                log.warning("Cannot play %s yet: %s", video.name, error)
            self.video_error = str(error)
            raise RuntimeError(str(error)) from error
        self.video_error = None
        self.player = Player(video.file, show, convert).start()
        self.player.started.wait(STARTED_S)
        if self.player.shown_on is None:
            raise RuntimeError(self.player.error or "the video's first frame is not on the screen yet")
        log.info("Playing %s on %s", video.name, self.player.shown_on)
        return self.player.shown_on

    def _quilt_player(self, video, calibration):
        """How a quilt video's frames are shown: interleaved by the GPU, if the screen has one, as decoded; otherwise
        by the processor, on the decoder's thread, which a Raspberry Pi 5 does about 10 times a second."""
        layout = Layout(video.columns, video.rows)
        if hasattr(self.screen, "show_quilt_frame"):
            return (lambda frame: self.screen.show_quilt_frame(frame, layout, calibration, video.reverse)), yuv_frames
        interleaver = self._interleaver(calibration, layout, video.width, video.height, video.reverse)
        return self.screen.show, (lambda frame: interleaver(frame.to_ndarray(format="rgb24")))

    def _stop_player(self):
        if self.player is not None:
            self.player.stop()
            self.player = None

    def _drop_video(self):
        """Stops the video: its file stays in the library."""
        self._stop_player()
        self.video, self.video_error = None, None

    def retry(self):
        """Shows the quilt or the video that could not be shown, if any: when the Looking Glass is plugged in, or
        switched on, after it. A video's player that has started tries again by itself."""
        with self.lock:
            try:
                if self.quilt is not None and self.shown_on is None:
                    self._show()
                elif self.video is not None and self.player is None:
                    self._play()
            except RuntimeError:
                pass

    def start(self):
        """Tries again, every RETRY_S, the quilt that could not be shown, until stop()."""
        def loop():
            while not self.stopping.is_set():
                self.retry()
                self.stopping.wait(RETRY_S)
        threading.Thread(target=loop, name="retry", daemon=True).start()

    def stop(self):
        self.stopping.set()
        with self.lock:
            self._stop_player()

    # What was shown last, to show it again after a restart: shown.json, with the library's id, or the test quilt.

    def _keep(self, shown):
        if self.state is None:
            return
        try:
            self.state.mkdir(parents=True, exist_ok=True)
            _write(self.state / SHOWN, json.dumps(shown).encode())
        except OSError as error:
            log.warning("Cannot keep what is shown in %s: %s", self.state, error)

    def _forget(self):
        if self.state is not None:
            (self.state / SHOWN).unlink(missing_ok=True)

    def restore(self):
        """Takes back what the last run showed, or else the default quilt, if any: start() shows it."""
        if self.state is None:
            self._take_default()
            return
        self._adopt_old_state()
        try:
            shown = json.loads((self.state / SHOWN).read_text()) if (self.state / SHOWN).exists() else None
        except (OSError, ValueError) as error:
            log.warning("Cannot read what was shown, %s: %s", self.state / SHOWN, error)
            shown = None
        if shown and shown.get("numbers"):
            picture = numbers_quilt()
            with self.lock:
                self.quilt = Quilt(NUMBERS, 8, 6, bool(shown.get("reverse")), picture.shape[1], picture.shape[0],
                                   _now(), None)
                self.picture = picture
            return
        item = self.library.find(id=shown.get("id")) if shown else None
        if item is None:
            self._take_default()
            return
        path = self.library.path(item)
        with self.lock:
            if item.is_video:
                self.video = Video(item.name, item.width, item.height, item.fps, item.frames, item.duration,
                                   item.codec, item.uploaded, str(path), item.columns, item.rows, item.reverse, item.id)
            else:
                try:
                    self.picture = read_quilt(path, item.name)
                except RuntimeError as error:
                    log.warning("Cannot take back %s: %s", item.name, error)
                    return
                self.quilt = Quilt(item.name, item.columns, item.rows, item.reverse, item.width, item.height,
                                   item.uploaded, str(path), item.id)
        log.info("Taking back %s, uploaded %s", item.name, item.uploaded)

    def _adopt_old_state(self):
        """Takes into the library the quilt or the video that a version before the library kept: quilt.json and its
        quilt.<suffix>, or video.json and its video.<suffix>."""
        for kind in ("quilt", "video"):
            index = self.state / f"{kind}.json"
            if not index.exists():
                continue
            try:
                kept = json.loads(index.read_text())
                if kind == "quilt" and kept.get("file") is None:  # The test quilt.
                    self._keep({"numbers": True, "reverse": bool(kept.get("reverse"))})
                else:
                    columns = kept.get("columns")
                    details = {"width": kept["width"], "height": kept["height"], "columns": columns,
                               "rows": kept.get("rows"), "reverse": bool(kept.get("reverse"))}
                    if kind == "video":
                        details.update(kind=QUILT_VIDEO if columns else HOLOGRAM_VIDEO, fps=kept.get("fps"),
                                       frames=kept.get("frames"), duration=kept.get("duration"),
                                       codec=kept.get("codec"))
                    else:
                        details["kind"] = QUILT
                    item = self.library.adopt(self.state / kept["file"], kept["name"], details, kept["uploaded"])
                    self._keep({"id": item.id})
                    log.info("Took %s into the library, as %s", item.name, item.id)
                index.unlink()
            except (OSError, ValueError, TypeError, KeyError) as error:
                log.warning("Cannot take the old %s of %s into the library: %s", kind, self.state, error)

    def _take_default(self):
        """The default quilt, not kept: an upload replaces it, and the next start shows it again."""
        if not self.default:
            return
        if self.default == NUMBERS:
            picture, layout, name = numbers_quilt(), Layout(8, 6), NUMBERS
        else:
            path = Path(self.default)
            layout = Layout.from_name(path)
            if layout is None:
                log.warning("No default quilt: no layout in the name %s, e.g. _qs8x6a0.75", path.name)
                return
            try:
                picture = read_quilt(path)
            except RuntimeError as error:
                log.warning("No default quilt: %s", error)
                return
            name = path.name
        with self.lock:
            self.quilt = Quilt(name, layout.columns, layout.rows, False, picture.shape[1], picture.shape[0], _now(),
                               None)
            self.picture = picture
        log.info("Showing the default quilt, %s", name)

    def status(self):
        with self.lock:
            calibration = self._calibration
            return {
                "version": __version__,
                "screen": self.screen.name,
                "looking_glass": None if calibration is None else
                {"serial": calibration.serial, "width": calibration.width, "height": calibration.height},
                "calibration_error": self.calibration_error,
                "display": self.display_status(),
            }

    def display_status(self):
        """What the Looking Glass shows, as the API answers it."""
        with self.lock:
            nothing = {"source": None, "media": None, "name": None, "kind": None, "reverse": False, "shown": False,
                       "shown_on": None, "error": None, "frame_rate": None, "decoder": None, "warning": None}
            if self.video is not None:
                video, player = self.video, self.player
                item = self.library.find(id=video.id)
                shown_on = player.shown_on if player else None
                rate = player.frame_rate() if player else None
                return dict(nothing, source=MEDIA, media=item and self.item_status(item), name=video.name,
                            kind=QUILT_VIDEO if video.columns else HOLOGRAM_VIDEO, reverse=video.reverse,
                            shown=shown_on is not None, shown_on=shown_on,
                            error=(player.error if player else self.video_error) if shown_on is None else None,
                            frame_rate=None if rate is None else round(rate, 1), decoder=player and player.decoding,
                            warning=codec_warning(video.codec))
            if self.quilt is not None:
                quilt = self.quilt
                item = self.library.find(id=quilt.id) if quilt.id else None
                source = MEDIA if quilt.id else TEST_PATTERN if quilt.name == NUMBERS else DEFAULT
                return dict(nothing, source=source, media=item and self.item_status(item), name=quilt.name,
                            kind=QUILT, reverse=quilt.reverse, shown=self.shown_on is not None,
                            shown_on=self.shown_on, error=self.error)
            return nothing

    def item_status(self, item):
        """A library's item, as the API answers it: shown, if it is on the Looking Glass now, not only waiting."""
        with self.lock:
            on_screen = (self.player is not None and self.player.shown_on is not None) if self.video is not None \
                else self.shown_on is not None
            return dict(asdict(item), warning=codec_warning(item.codec) if item.is_video else None,
                        shown=self.shown_id() == item.id and on_screen)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sentence(error):
    text = str(error)
    return text if text.endswith((".", "?", "!")) else text + "."


def _write(path, data):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


# The API.

DESCRIPTION = """
Shows quilts and videos on a **Looking Glass Portrait** as holograms, from any computer on the network.

The server keeps a **library** of media on its disk: quilts, images of a grid of views, and videos of quilts, or of
holograms already interleaved for this Looking Glass. Upload one with `POST /api/media`, and show it on the
**display** with `PUT /api/display`, by its id or its name, at once, as nothing is uploaded again. The server
interleaves it for the Looking Glass, with the calibration on the display's own USB drive, on its GPU, and shows it
full-screen until something else replaces it, also after a restart.

```bash
curl -F file=@helix_qs8x6a0.75.mp4 http://holo.local:8095/api/media
curl -X PUT -H "Content-Type: application/json" -d '{"media_name": "helix_qs8x6a0.75.mp4"}' http://holo.local:8095/api/display
```

`POST /api/media` with `play=true` uploads and shows in one request. A quilt's layout comes from its file's name, as
Looking Glass's tools read it, e.g. `_qs8x6a0.75` for 8 columns and 6 rows, or from the fields `columns` and `rows`;
a video with no layout is a hologram video.

Every error answers `{"error": "<what went wrong, and what to check>"}`. There is no authentication: keep the
server on a network you trust. **Try it out** changes what the Looking Glass shows, and the library on its disk.
"""

TAGS = [
    {"name": "media", "description": "The library: the quilts and videos kept on the server's disk. Upload, list, "
                                     "download and remove them."},
    {"name": "display", "description": "What the Looking Glass shows: a medium of the library, the test pattern, "
                                       "or black."},
    {"name": "server", "description": "The server, the screen and the Looking Glass's calibration."},
]


class LookingGlassModel(BaseModel):
    serial: str = Field(description="The serial number of the Looking Glass, from its calibration.",
                        examples=["LKG-PORT-00671"])
    width: int = Field(description="Its screen's width, in pixels.", examples=[1536])
    height: int = Field(description="Its screen's height, in pixels.", examples=[2048])


class MediaModel(BaseModel):
    id: str = Field(description="The medium's id, which addresses it: /api/media/{id}.", examples=["3f9a1c2e"])
    name: str = Field(description="Its file's name, as uploaded: unique in the library, so that it addresses it "
                                  "too.", examples=["helix_qs8x6a0.75.mp4"])
    kind: str = Field(description="quilt, an image of a grid of views; quilt video, a video whose every frame is a "
                                  "quilt; or hologram video, a video interleaved already for this Looking Glass.",
                      examples=["quilt video"])
    size: int = Field(description="Its file's size, in bytes.", examples=[122438702])
    uploaded: str = Field(description="When it was uploaded, in UTC, ISO 8601.", examples=["2026-11-17T11:45:02+00:00"])
    width: int = Field(description="Its width, or its frames', in pixels.", examples=[3360])
    height: int = Field(description="Its height, or its frames', in pixels.", examples=[3360])
    columns: Optional[int] = Field(None, description="A quilt's columns of views; null for a hologram video.",
                                   examples=[8])
    rows: Optional[int] = Field(None, description="A quilt's rows of views; null for a hologram video.", examples=[6])
    reverse: bool = Field(False, description="Whether its views are shown in the other order.")
    fps: Optional[float] = Field(None, description="A video's frames a second, if its file says.", examples=[24.0])
    frames: Optional[int] = Field(None, description="A video's number of frames, if its file says.", examples=[480])
    duration: Optional[float] = Field(None, description="A video's length, in seconds, if its file says.",
                                      examples=[20.0])
    codec: Optional[str] = Field(None, description="How a video is encoded.", examples=["hevc"])
    warning: Optional[str] = Field(None, description="What to change: for a video not in H.265 (HEVC), which a "
                                                     "Raspberry Pi 5 decodes on its processor, maybe too slowly.")
    shown: bool = Field(description="Whether the Looking Glass shows it now.")


class MediaListModel(BaseModel):
    items: list[MediaModel] = Field(description="The library's media, in the order they were first uploaded.")
    size: int = Field(description="The bytes they take, together.", examples=[512000000])
    free: int = Field(description="The bytes left on the disk, for more.", examples=[200000000000])


class DisplayModel(BaseModel):
    source: Optional[str] = Field(None, description="Where what is shown comes from: media, the library; test "
                                                    "pattern; default, the server's default quilt; or null, black.",
                                  examples=["media"])
    media: Optional[MediaModel] = Field(None, description="The medium shown, if it comes from the library.")
    name: Optional[str] = Field(None, description="The name of what is shown.", examples=["helix_qs8x6a0.75.mp4"])
    kind: Optional[str] = Field(None, description="quilt, quilt video or hologram video.", examples=["quilt video"])
    reverse: bool = Field(False, description="Whether its views are shown in the other order.")
    shown: bool = Field(description="Whether it is on the Looking Glass now: false while the Looking Glass is "
                                    "unplugged or off, until it is back.")
    shown_on: Optional[str] = Field(None, description="Where.", examples=["HDMI-A-1 of /dev/dri/card1, 1536 x 2048, "
                                                                         "through the GPU"])
    error: Optional[str] = Field(None, description="Why it is not shown yet, e.g. no Looking Glass found. It is "
                                                   "tried again every 5 seconds.")
    frame_rate: Optional[float] = Field(None, description="A video's frames shown a second, lately: its fps when the "
                                                          "server keeps up, less when it does not.", examples=[23.6])
    decoder: Optional[str] = Field(None, description="What decodes a video: hardware, e.g. a Raspberry Pi 5's HEVC "
                                                     "decoder, or software, the processor.", examples=["hardware"])
    warning: Optional[str] = Field(None, description="What to change, for a video not in H.265 (HEVC).")


class DisplayRequest(BaseModel):
    media_id: Optional[str] = Field(None, description="Show the library's medium of this id.", examples=["3f9a1c2e"])
    media_name: Optional[str] = Field(None, description="Show the library's medium of this name.",
                                      examples=["helix_qs8x6a0.75.mp4"])
    test_pattern: bool = Field(False, description="Show the test pattern: 48 views, each showing its number. Through "
                                                  "the lenses, one number fills the screen; a mix of numbers means "
                                                  "that the calibration is wrong.")
    reverse: bool = Field(False, description="With test_pattern, its views in the other order.")


class StatusModel(BaseModel):
    version: str = Field(description="The version of HoloPi.", examples=[__version__])
    screen: str = Field(description="How it shows: gl, through the GPU; drm, straight to the screen; desktop, in a "
                                    "full-screen window.", examples=["gl"])
    looking_glass: Optional[LookingGlassModel] = Field(None, description="The Looking Glass, once its calibration "
                                                                         "has been read.")
    calibration_error: Optional[str] = Field(None, description="Why the calibration could not be read, if so.")
    display: DisplayModel = Field(description="What the Looking Glass shows.")


class CalibrationModel(BaseModel):
    serial: str = Field(description="The serial number of the Looking Glass.")
    width: int = Field(description="The screen's width, in pixels.")
    height: int = Field(description="The screen's height, in pixels.")
    pitch: float = Field(description="Lenses across the screen's width, along their slant.")
    tilt: float = Field(description="How far the lenses slant: the horizontal shift per screen height, in "
                                    "screen widths.")
    center: float = Field(description="Where view 0 starts under a lens, as a fraction of a lens.")
    subp: float = Field(description="The width of a sub-pixel, as a fraction of the screen's width.")
    inverted: bool = Field(description="Whether the views go from right to left under each lens.")


class ErrorModel(BaseModel):
    error: str = Field(description="What went wrong, and what to check.", examples=["no medium of the id '3f9a1c2e'"])


def error(status, description):
    return {status: {"model": ErrorModel, "description": description}}


NOT_FOUND = error(404, "No medium of this id.")
NOT_YET = error(503, "Not shown yet: no Looking Glass, or no screen of its size. It is shown as soon as it can be.")


def create_app(display, web=None):
    """The FastAPI application: the API on /api, its documentation on /api/docs, and the web page of the folder
    `web`, if any, on /."""
    app = FastAPI(title="HoloPi", version=__version__, description=DESCRIPTION, openapi_tags=TAGS,
                  openapi_url="/api/openapi.json", docs_url=None, redoc_url=None)

    @app.exception_handler(StarletteHTTPException)
    def http_error(request, exception):
        return JSONResponse({"error": str(exception.detail)}, status_code=exception.status_code,
                            headers=getattr(exception, "headers", None))

    @app.exception_handler(RequestValidationError)
    def invalid_request(request, exception):
        problems = "; ".join(f"{'.'.join(str(part) for part in problem['loc'])}: {problem['msg']}"
                             for problem in exception.errors())
        return JSONResponse({"error": f"invalid request: {problems}"}, status_code=422)

    # The documentation: Swagger UI, from its files on this server when the web page brings them, so that it works
    # on a network without the internet.
    swagger = Path(web) / "swagger-ui" if web else None
    has_swagger = swagger is not None and (swagger / "swagger-ui-bundle.js").exists()
    if has_swagger:
        app.mount("/api/docs/assets", StaticFiles(directory=swagger), name="swagger-ui")

    @app.get("/api/docs", include_in_schema=False)
    def docs():
        assets = {"swagger_js_url": "/api/docs/assets/swagger-ui-bundle.js",
                  "swagger_css_url": "/api/docs/assets/swagger-ui.css"} if has_swagger else {}
        return get_swagger_ui_html(openapi_url=app.openapi_url, title="HoloPi API", **assets)

    # The library.

    def find(id):
        item = display.library.find(id=id)
        if item is None:
            raise HTTPException(404, f"no medium of the id {id!r}")
        return item

    @app.get("/api/media", tags=["media"], response_model=MediaListModel, summary="List the media")
    def list_media():
        """Every quilt and video of the library, with the space they take and the space left on the disk."""
        items = display.library.list()
        return {"items": [display.item_status(item) for item in items], "size": sum(item.size for item in items),
                "free": display.library.free()}

    @app.post("/api/media", tags=["media"], response_model=MediaModel, status_code=201, summary="Upload a medium",
              responses={200: {"model": MediaModel, "description": "It replaced the medium of the same name, and "
                                                                   "kept its id."},
                         **error(400, "Not an image or a video, a quilt of no known layout, only one of columns "
                                      "and rows, or a hologram video not of the Looking Glass's size."),
                         **error(501, "A video, and the server has no PyAV, python3-av.")})
    def upload_media(
        response: Response,
        file: UploadFile = File(description="The quilt, an image, e.g. helix_qs8x6a0.75.jpg; the quilt video, "
                                            "e.g. helix_qs8x6a0.75.mp4; or the hologram video, of the screen's "
                                            "size or twice as wide, e.g. Anna.jpg__lkgrec.mp4. HEVC plays best."),
        columns: Optional[int] = Form(None, ge=1, description="Its columns of views, if its name does not say, "
                                                              "e.g. 8."),
        rows: Optional[int] = Form(None, ge=1, description="Its rows of views, if its name does not say, e.g. 6."),
        reverse: bool = Form(False, description="Show its views in the other order, if the depth looks inside "
                                                "out."),
        play: bool = Form(False, description="Show it at once, too, as PUT /api/display would. Whether it is shown "
                                             "is in the answer's shown, and GET /api/display says why not."),
    ):
        """Keeps a quilt or a video in the library, to show it with PUT /api/display. It answers 201 with its
        Location, or 200 if it replaced the medium of the same name. Without play, what the Looking Glass shows does
        not change."""
        name = file.filename or "upload"
        replaced = display.library.find(name=name) is not None
        try:
            item = display.store(file.file, name, columns, rows, reverse)
        except (QuiltError, VideoError) as problem:
            raise HTTPException(400, str(problem)) from problem
        except NoPyAV as problem:
            raise HTTPException(501, str(problem)) from problem
        if play:
            try:
                display.play_item(item)
            except RuntimeError:
                pass  # Kept, and shown as soon as it can be: GET /api/display says why not yet.
        response.status_code = 200 if replaced else 201
        response.headers["Location"] = f"/api/media/{item.id}"
        return display.item_status(item)

    @app.delete("/api/media", tags=["media"], status_code=204, summary="Remove every medium")
    def remove_all_media():
        """Empties the library, its files too. If the Looking Glass shows one of them, it shows black."""
        display.remove_all()
        return Response(status_code=204)

    @app.get("/api/media/{id}", tags=["media"], response_model=MediaModel, summary="Get a medium",
             responses=NOT_FOUND)
    def get_medium(id: str = FastApiPath(description="The medium's id.", examples=["3f9a1c2e"])):
        """What the library's medium of this id is."""
        return display.item_status(find(id))

    @app.get("/api/media/{id}/content", tags=["media"], summary="Download a medium",
             responses={200: {"content": {"image/*": {}, "video/*": {}}, "description": "Its file, as uploaded, "
                                                                                       "with its name."},
                        **NOT_FOUND})
    def get_content(id: str = FastApiPath(description="The medium's id.", examples=["3f9a1c2e"])):
        """The library's medium of this id, its file as uploaded."""
        item = find(id)
        return FileResponse(display.library.path(item), filename=item.name)

    @app.delete("/api/media/{id}", tags=["media"], status_code=204, summary="Remove a medium", responses=NOT_FOUND)
    def remove_medium(id: str = FastApiPath(description="The medium's id.", examples=["3f9a1c2e"])):
        """Removes the library's medium of this id, its file too. If the Looking Glass shows it, it shows black."""
        display.remove(find(id))
        return Response(status_code=204)

    # The display.

    @app.get("/api/display", tags=["display"], response_model=DisplayModel, summary="Get what is shown")
    def get_display():
        """What the Looking Glass shows, whether it is on the screen, and, for a video, how fast it plays."""
        return display.display_status()

    @app.put("/api/display", tags=["display"], response_model=DisplayModel, summary="Show a medium",
             responses={**error(400, "Not one of media_id, media_name and test_pattern."),
                        **error(404, "No medium of this id or name."), **NOT_YET})
    def put_display(request: DisplayRequest):
        """Shows the library's quilt, or plays its video in a loop, by its id or its name, or the test pattern: at
        once, as nothing is uploaded. It answers once it is on the Looking Glass, a video's first frame too; it
        stays, also after a restart, until something else replaces it."""
        if [request.media_id is not None, request.media_name is not None, request.test_pattern].count(True) != 1:
            raise HTTPException(400, "give one of media_id, media_name and test_pattern, e.g. "
                                     '{"media_name": "helix_qs8x6a0.75.mp4"}')
        try:
            if request.test_pattern:
                display.show_test_pattern(request.reverse)
            else:
                display.play(request.media_id, request.media_name)
        except KeyError as problem:
            raise HTTPException(404, problem.args[0]) from problem
        except RuntimeError as problem:
            raise HTTPException(503, f"{_sentence(problem)} It is kept, and shown as soon as it can be.") from problem
        return display.display_status()

    @app.delete("/api/display", tags=["display"], status_code=204, summary="Show black")
    def clear_display():
        """Shows black on the Looking Glass: what it showed stays in the library."""
        display.clear()
        return Response(status_code=204)

    # The server.

    @app.get("/api/status", tags=["server"], response_model=StatusModel, summary="Get the server's status")
    def status():
        """The version, the screen, the Looking Glass, and what it shows."""
        return display.status()

    @app.get("/api/calibration", tags=["server"], response_model=CalibrationModel,
             summary="Get the Looking Glass's calibration",
             responses=error(503, "No calibration: the Looking Glass's drive is not there."))
    def calibration():
        """The values the interleaving derives from the Looking Glass's visual.json, as `holo-pi calibration` prints
        them."""
        try:
            return asdict(display.calibration())
        except RuntimeError as problem:
            raise HTTPException(503, str(problem)) from problem

    # The web page, on everything else: its files, and index.html for its own paths.

    if web and (Path(web) / "index.html").exists():
        app.mount("/", StaticFiles(directory=web, html=True), name="web")
    else:
        @app.get("/", include_in_schema=False)
        def home():
            return RedirectResponse("/api/docs")

    return app


def web_folder():
    """The web page's built files: $HOLO_PI_WEB, e.g. in the container, or else web/dist of the checkout."""
    return Path(os.environ.get("HOLO_PI_WEB") or Path(__file__).resolve().parents[1] / "web" / "dist")


def serve(host="0.0.0.0", port=8095, screen="auto", calibration=None, state=None, mount=False, default=None,
          web=None):
    """Runs the server until it is interrupted or terminated. Returns the exit code."""
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s", force=True)
    screen = open_screen(screen, closable=False)
    display = Display(screen, calibration=calibration, state=state or state_folder(), mount=mount, default=default)
    display.restore()
    web = Path(web) if web else web_folder()
    if not (web / "index.html").exists():
        log.info("No web page in %s: build it with pnpm build in web/", web)
    server = uvicorn.Server(uvicorn.Config(create_app(display, web), host=host, port=port, log_level="info"))
    stop = threading.Event()

    def run_server():
        try:
            server.run()
        finally:
            stop.set()  # e.g. the port is taken: stop the screen too.

    thread = threading.Thread(target=run_server, name="uvicorn", daemon=True)
    thread.start()
    display.start()
    log.info("HoloPi %s on %s, showing through %s", __version__, f"http://{host}:{port}", screen.name)
    try:
        screen.run(stop)
    finally:
        server.should_exit = True
        display.stop()
        thread.join(5)
        screen.close()
    return 0 if server.started else 1
