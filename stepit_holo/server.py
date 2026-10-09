"""The HTTP server: any computer on the network shows a quilt on the Looking Glass by uploading it.

`stepit-holo serve` runs it: FastAPI, served by uvicorn on a thread of its own,
while the main thread runs the screen, GTK's loop on a desktop. Display holds
what is shown: it reads the calibration once it is there, keeps the table of
the last layouts in memory, and keeps the last quilt on disk, to show it again
after a restart. A quilt that cannot be shown yet, e.g. because the Looking
Glass is switched off, is kept, and shown as soon as it can be.

See docs/API.md for the API, and http://<host>:8095/docs for the same, live.
"""

import io
import json
import logging
import os
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from PIL import Image
from pydantic import BaseModel, Field

from . import __version__
from .calibration import find_calibration, load_calibration, mount_drives
from .interleave import Interleaver
from .layout import Layout
from .numbers import numbers_quilt
from .quilt import read_quilt
from .screen import open_screen

log = logging.getLogger(__name__)

# How often a quilt that could not be shown is tried again.
RETRY_S = 5
# The tables kept in memory, about 38 MB each for a Portrait: one per layout and size of quilt.
TABLES = 2
NUMBERS = "numbers"
KEPT = "The quilt is kept, and shown as soon as it can be."
SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def state_folder():
    base = os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state"
    return Path(base) / "stepit-holo"


class QuiltError(ValueError):
    """A quilt that cannot be shown whatever the Looking Glass: not an image, or of no known layout."""


@dataclass
class Quilt:
    name: str  # As uploaded, e.g. wasp_qs8x6a0.75.jpg, or "numbers" for the test quilt.
    columns: int
    rows: int
    reverse: bool
    width: int
    height: int
    uploaded: str  # UTC, ISO 8601.
    file: Optional[str]  # Its copy in the state folder; None for the test quilt, which is drawn again.


class Display:
    """What the Looking Glass shows, and the calibration it is shown with. Thread-safe."""

    def __init__(self, screen, calibration=None, state=None, mount=False):
        self.screen = screen
        self.calibration_path = calibration
        self.state = Path(state) if state else None
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
        self.stopping = threading.Event()

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

    def _interleaver(self, calibration, layout, width, height, reverse):
        key = (calibration, layout, width, height, reverse)
        interleaver = self.tables.pop(key, None) or Interleaver(calibration, layout, width, height, reverse)
        self.tables[key] = interleaver  # The most recent last.
        while len(self.tables) > TABLES:
            self.tables.pop(next(iter(self.tables)))
        return interleaver

    # What is shown.

    def show_quilt(self, data, name, columns=None, rows=None, reverse=False):
        """Shows the quilt in `data`, the bytes of an image file. Raises QuiltError if it is not a quilt, and
        RuntimeError if it cannot be shown yet: it is kept, and shown as soon as it can be."""
        if (columns is None) != (rows is None):
            raise QuiltError("give both columns and rows, or neither")
        layout = Layout(columns, rows) if columns else Layout.from_name(name)
        if layout is None:
            raise QuiltError(f"no layout in the name {name!r}, e.g. _qs8x6a0.75: give columns and rows")
        try:
            picture = read_quilt(io.BytesIO(data), name)
        except RuntimeError as error:
            raise QuiltError(str(error)) from error
        with self.lock:
            self._set(Quilt(name, layout.columns, layout.rows, reverse, picture.shape[1], picture.shape[0],
                            _now(), None), picture, data)
            return self._show()

    def show_numbers(self, reverse=False):
        """Shows the test quilt of numbered views."""
        picture = numbers_quilt()
        with self.lock:
            self._set(Quilt(NUMBERS, 8, 6, reverse, picture.shape[1], picture.shape[0], _now(), None), picture)
            return self._show()

    def clear(self):
        """Forgets the quilt, and shows black."""
        with self.lock:
            self.quilt, self.picture, self.shown_on, self.error = None, None, None, None
            self._forget()
            self.screen.clear()

    def _set(self, quilt, picture, data=None):
        self.quilt, self.picture, self.shown_on, self.error = quilt, picture, None, None
        self._keep(quilt, data)

    def _show(self):
        quilt = self.quilt
        try:
            calibration = self.calibration()
            layout = Layout(quilt.columns, quilt.rows)
            hologram = self._interleaver(calibration, layout, quilt.width, quilt.height, quilt.reverse)(self.picture)
            self.shown_on = self.screen.show(hologram)
            self.error = None
            log.info("Showing %s on %s", quilt.name, self.shown_on)
            return self.shown_on
        except RuntimeError as error:
            if str(error) != self.error:
                log.warning("Cannot show %s yet: %s", quilt.name, error)
            self.error = str(error)
            raise

    def retry(self):
        """Shows the quilt that could not be shown, if any: when the Looking Glass is plugged in, or switched
        on, after it."""
        with self.lock:
            if self.quilt is not None and self.shown_on is None:
                try:
                    self._show()
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

    # The state folder: the last quilt, to show it again after a restart.

    def _keep(self, quilt, data):
        if self.state is None:
            return
        try:
            self.state.mkdir(parents=True, exist_ok=True)
            self._forget()
            if data is not None:
                suffix = Path(quilt.name).suffix.lower()
                quilt.file = "quilt" + (suffix if suffix in SUFFIXES else "")
                _write(self.state / quilt.file, data)
            _write(self.state / "quilt.json", json.dumps(asdict(quilt), indent=2).encode())
        except OSError as error:
            log.warning("Cannot keep the quilt in %s: %s", self.state, error)

    def _forget(self):
        if self.state is None:
            return
        for path in self.state.glob("quilt*"):
            path.unlink(missing_ok=True)

    def restore(self):
        """Takes back the quilt kept by the last run, if any: start() shows it."""
        if self.state is None or not (self.state / "quilt.json").exists():
            return
        try:
            quilt = Quilt(**json.loads((self.state / "quilt.json").read_text()))
            picture = numbers_quilt() if quilt.file is None else read_quilt(self.state / quilt.file, quilt.name)
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            log.warning("Cannot take back the last quilt from %s: %s", self.state, error)
            return
        with self.lock:
            self.quilt, self.picture = quilt, picture
        log.info("Taking back %s, uploaded %s", quilt.name, quilt.uploaded)

    def quilt_file(self):
        """The path of the quilt's copy, or None."""
        with self.lock:
            if self.quilt is None or self.quilt.file is None or self.state is None:
                return None
            return self.state / self.quilt.file

    def status(self):
        with self.lock:
            calibration = self._calibration
            return {
                "version": __version__,
                "screen": self.screen.name,
                "looking_glass": None if calibration is None else
                {"serial": calibration.serial, "width": calibration.width, "height": calibration.height},
                "calibration_error": self.calibration_error,
                "quilt": self.quilt_status(),
            }

    def quilt_status(self):
        with self.lock:
            if self.quilt is None:
                return None
            quilt = asdict(self.quilt)
            del quilt["file"]
            return dict(quilt, shown=self.shown_on is not None, shown_on=self.shown_on, error=self.error)


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
Shows quilts on a **Looking Glass Portrait** as holograms, from any computer on the network.

Upload a quilt with `POST /quilt`: the server interleaves it for the Looking Glass, with the calibration on the
display's own USB drive, and shows it full-screen, pixel for pixel, until the next quilt replaces it. It shows it
again after a restart.

```bash
curl -F file=@wasp_qs8x6a0.75.jpg http://raspberrypi.local:8095/quilt
```

The layout comes from the file's name, as Looking Glass's tools read it, e.g. `_qs8x6a0.75` for 8 columns and
6 rows, or from the fields `columns` and `rows`.

There is no authentication: keep the server on a network you trust.
"""

TAGS = [
    {"name": "quilt", "description": "The quilt on the Looking Glass: upload one, read it back, or remove it."},
    {"name": "looking glass", "description": "The server, the screen and the Looking Glass's calibration."},
]


class LookingGlassModel(BaseModel):
    serial: str = Field(description="The serial number of the Looking Glass, from its calibration.")
    width: int = Field(description="Its screen's width, in pixels, e.g. 1536 for a Portrait.")
    height: int = Field(description="Its screen's height, in pixels, e.g. 2048 for a Portrait.")


class QuiltModel(BaseModel):
    name: str = Field(description="The quilt's file name, as uploaded, e.g. wasp_qs8x6a0.75.jpg, or numbers for "
                                  "the test quilt.")
    columns: int = Field(description="The columns of views in the quilt.")
    rows: int = Field(description="The rows of views in the quilt.")
    reverse: bool = Field(description="Whether its views are shown in the other order.")
    width: int = Field(description="The quilt's width, in pixels.")
    height: int = Field(description="The quilt's height, in pixels.")
    uploaded: str = Field(description="When it was uploaded, in UTC, ISO 8601, e.g. 2026-10-09T14:03:22+00:00.")
    shown: bool = Field(description="Whether it is on the Looking Glass now.")
    shown_on: Optional[str] = Field(None, description="Where it is shown, e.g. HDMI-A-1 of /dev/dri/card1, "
                                                      "1536 x 2048.")
    error: Optional[str] = Field(None, description="Why it is not shown yet, e.g. no Looking Glass found. It is "
                                                   "tried again every 5 seconds.")


class StatusModel(BaseModel):
    version: str = Field(description="The version of StepIt Holo.")
    screen: str = Field(description="How it shows: drm, straight to the screen, without a desktop, or desktop, "
                                    "in a full-screen window.")
    looking_glass: Optional[LookingGlassModel] = Field(None, description="The Looking Glass, once its "
                                                                         "calibration has been read.")
    calibration_error: Optional[str] = Field(None, description="Why the calibration could not be read, if so.")
    quilt: Optional[QuiltModel] = Field(None, description="The quilt to show, if any.")


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
    detail: str = Field(description="What went wrong, and what to check.")


def create_app(display):
    """The FastAPI application that shows quilts on `display`."""
    app = FastAPI(title="StepIt Holo", version=__version__, description=DESCRIPTION, openapi_tags=TAGS)

    @app.get("/", include_in_schema=False)
    def home():
        return RedirectResponse("/docs")

    @app.get("/status", tags=["looking glass"], response_model=StatusModel, summary="What the server shows")
    def status():
        """The screen, the Looking Glass, and the quilt to show, if any, with whether it is shown."""
        return display.status()

    @app.get("/calibration", tags=["looking glass"], response_model=CalibrationModel,
             summary="The Looking Glass's calibration",
             responses={503: {"model": ErrorModel, "description": "No calibration: the Looking Glass's drive is "
                                                                  "not there."}})
    def calibration():
        """The values the interleaving derives from the Looking Glass's `visual.json`, as
        `stepit-holo calibration` prints them."""
        try:
            return asdict(display.calibration())
        except RuntimeError as error:
            raise HTTPException(503, str(error)) from error

    @app.post("/quilt", tags=["quilt"], response_model=QuiltModel, summary="Show a quilt",
              responses={400: {"model": ErrorModel, "description": "Not an image, or of no known layout."},
                         503: {"model": ErrorModel, "description": "Kept, but not shown yet: no Looking Glass, "
                                                                   "or no screen of its size. It is shown as "
                                                                   "soon as it can be."}})
    def show_quilt(
        file: UploadFile = File(description="The quilt: a PNG, JPEG or any image Pillow reads, e.g. "
                                            "wasp_qs8x6a0.75.jpg."),
        columns: Optional[int] = Form(None, ge=1, description="The columns of views, if the file's name does "
                                                              "not say, e.g. 8."),
        rows: Optional[int] = Form(None, ge=1, description="The rows of views, if the file's name does not "
                                                           "say, e.g. 6."),
        reverse: bool = Form(False, description="Show the views in the other order, if the depth looks inside "
                                                "out."),
    ):
        """Shows the quilt on the Looking Glass, in place of the one before, and keeps it, to show it again
        after a restart. It answers once the quilt is on the screen: a few hundred milliseconds, or a few
        seconds for the first quilt of a layout, whose table is worked out first."""
        try:
            display.show_quilt(file.file.read(), file.filename or "quilt", columns, rows, reverse)
        except QuiltError as error:
            raise HTTPException(400, str(error)) from error
        except RuntimeError as error:
            raise HTTPException(503, f"{_sentence(error)} {KEPT}") from error
        return display.quilt_status()

    @app.get("/quilt", tags=["quilt"], summary="The quilt shown",
             responses={200: {"content": {"image/*": {}}, "description": "The quilt, as uploaded."},
                        404: {"model": ErrorModel, "description": "No quilt."}})
    def get_quilt():
        """The quilt the Looking Glass shows, or will show, as it was uploaded; the test quilt as a PNG."""
        quilt = display.quilt_status()
        if quilt is None:
            raise HTTPException(404, "no quilt")
        path = display.quilt_file()
        if path is not None and path.exists():
            return FileResponse(path, filename=quilt["name"])
        buffer = io.BytesIO()
        Image.fromarray(numbers_quilt() if quilt["name"] == NUMBERS else display.picture).save(buffer, "PNG")
        return Response(buffer.getvalue(), media_type="image/png")

    @app.delete("/quilt", tags=["quilt"], status_code=204, summary="Remove the quilt")
    def remove_quilt():
        """Forgets the quilt, and shows black on the Looking Glass."""
        display.clear()
        return Response(status_code=204)

    @app.post("/numbers", tags=["quilt"], response_model=QuiltModel, summary="Show the test quilt",
              responses={503: {"model": ErrorModel, "description": "Kept, but not shown yet."}})
    def show_numbers(reverse: bool = False):
        """Shows a test quilt whose 48 views each show their number. Through the lenses, one number fills the
        screen, and changes in order as you move sideways; a mix of numbers means the calibration is wrong."""
        try:
            display.show_numbers(reverse)
        except RuntimeError as error:
            raise HTTPException(503, f"{_sentence(error)} {KEPT}") from error
        return display.quilt_status()

    return app


def serve(host="0.0.0.0", port=8095, screen="auto", calibration=None, state=None, mount=False):
    """Runs the server until it is interrupted or terminated. Returns the exit code."""
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s", force=True)
    screen = open_screen(screen, closable=False)
    display = Display(screen, calibration=calibration, state=state or state_folder(), mount=mount)
    display.restore()
    server = uvicorn.Server(uvicorn.Config(create_app(display), host=host, port=port, log_level="info"))
    stop = threading.Event()

    def run_server():
        try:
            server.run()
        finally:
            stop.set()  # e.g. the port is taken: stop the screen too.

    thread = threading.Thread(target=run_server, name="uvicorn", daemon=True)
    thread.start()
    display.start()
    log.info("StepIt Holo %s on %s, showing through %s", __version__, f"http://{host}:{port}", screen.name)
    try:
        screen.run(stop)
    finally:
        server.should_exit = True
        display.stop()
        thread.join(5)
        screen.close()
    return 0 if server.started else 1
