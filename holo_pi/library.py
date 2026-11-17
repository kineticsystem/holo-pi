"""The library: the quilts and videos kept on the computer, to show by their id or their name.

Every upload goes into the library, POST /api/media, whether it is shown at once,
with play, or only kept, to show later with PUT /api/display. Each item is a file
in the library's folder, <id><suffix>, and an entry of index.json, which says
what it is:

- a quilt, an image of the layout its name gives, e.g. _qs8x6a0.75, or its fields;
- a quilt video, a video with a layout, each frame a quilt;
- a hologram video, a video without a layout, interleaved already for one Looking
  Glass, of its screen's size or twice as wide.

A name is unique: an upload of a name the library has replaces that item, and
keeps its id, so that what refers to it still does.
"""

import json
import logging
import os
import re
import secrets
import shutil
import tempfile
import threading
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from PIL import Image

from .layout import Layout
from .video import VideoError, probe, step

log = logging.getLogger(__name__)

QUILT, QUILT_VIDEO, HOLOGRAM_VIDEO = "quilt", "quilt video", "hologram video"
INDEX = "index.json"


class QuiltError(ValueError):
    """A quilt that cannot be shown whatever the Looking Glass: not an image, or of no known layout."""


@dataclass
class Item:
    id: str  # e.g. 3f9a1c2e: what to play it by, as its name.
    name: str  # As uploaded, e.g. helix_qs8x6a0.75.mp4: unique in the library.
    kind: str  # QUILT, QUILT_VIDEO or HOLOGRAM_VIDEO.
    file: str  # In the library's folder, e.g. 3f9a1c2e.mp4.
    size: int  # In bytes.
    uploaded: str  # UTC, ISO 8601.
    width: int
    height: int
    columns: Optional[int] = None  # A quilt's layout, or a quilt video's; None for a hologram video.
    rows: Optional[int] = None
    reverse: bool = False
    fps: Optional[float] = None  # A video's, if its file says.
    frames: Optional[int] = None
    duration: Optional[float] = None  # In seconds.
    codec: Optional[str] = None  # A video's, e.g. hevc.

    @property
    def layout(self):
        return Layout(self.columns, self.rows) if self.columns else None

    @property
    def is_video(self):
        return self.kind != QUILT


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Library:
    """The items kept in `folder`. Thread-safe."""

    def __init__(self, folder):
        self.folder = Path(folder)
        self.lock = threading.RLock()
        self.items = {}  # By id, in the order they were added.
        self._load()

    def _load(self):
        path = self.folder / INDEX
        if not path.exists():
            return
        try:
            known = {field.name for field in fields(Item)}
            for entry in json.loads(path.read_text()):
                item = Item(**{key: value for key, value in entry.items() if key in known})
                if (self.folder / item.file).exists():
                    self.items[item.id] = item
                else:
                    log.warning("The library has no file %s for %s: forgotten", item.file, item.name)
        except (OSError, ValueError, TypeError) as error:
            log.warning("Cannot read the library's index %s: %s", path, error)

    def _save(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        data = json.dumps([asdict(item) for item in self.items.values()], indent=2).encode()
        temporary = self.folder / (INDEX + ".tmp")
        temporary.write_bytes(data)
        temporary.replace(self.folder / INDEX)

    # Reading it.

    def list(self):
        with self.lock:
            return list(self.items.values())

    def find(self, id=None, name=None):
        """The item of this id, or else of this name; None if there is none."""
        with self.lock:
            if id is not None:
                return self.items.get(id)
            return next((item for item in self.items.values() if item.name == name), None)

    def path(self, item):
        return self.folder / item.file

    def free(self):
        """The bytes left on the library's disk."""
        self.folder.mkdir(parents=True, exist_ok=True)
        return shutil.disk_usage(self.folder).free

    # Changing it.

    def add(self, source, name, columns=None, rows=None, reverse=False, screen=None):
        """Keeps the upload in `source`, a binary file, as `name`: a quilt or a video, see the module. `screen`, the
        Looking Glass's (width, height), if known, checks a hologram video's size. Returns the item. Raises
        QuiltError or VideoError if it cannot be shown whatever the Looking Glass, and NoPyAV for a video without
        PyAV."""
        if (columns is None) != (rows is None):
            raise QuiltError("give both columns and rows, or neither")
        layout = Layout(columns, rows) if columns else Layout.from_name(name)
        suffix = Path(name).suffix.lower()
        suffix = suffix if re.fullmatch(r"\.[a-z0-9]{1,8}", suffix) else ""
        self.folder.mkdir(parents=True, exist_ok=True)
        # A name of its own, so that two uploads at once do not write into the same file.
        handle, upload = tempfile.mkstemp(".tmp", "upload-", self.folder)
        upload = Path(upload)
        try:
            with os.fdopen(handle, "wb") as file:
                shutil.copyfileobj(source, file, 1 << 20)
            details = self._inspect(upload, name, layout, screen)
        except BaseException:
            upload.unlink(missing_ok=True)
            raise
        with self.lock:
            before = self.find(name=name)
            id = before.id if before else self._new_id()
            if before is not None:
                self.path(before).unlink(missing_ok=True)
            file = f"{id}{suffix}"
            upload.replace(self.folder / file)
            item = Item(id=id, name=name, file=file, size=(self.folder / file).stat().st_size, uploaded=now(),
                        reverse=bool(layout and reverse), **details)
            self.items.pop(id, None)
            self.items[id] = item
            self._save()
        log.info("Kept %s, %s, as %s", name, item.kind, id)
        return item

    def _inspect(self, path, name, layout, screen):
        """What the upload at `path` is: the fields of its Item but its id, name, file, size and time."""
        try:
            with Image.open(path) as image:
                image.verify()
                width, height = image.size
        except (OSError, Image.DecompressionBombError, SyntaxError):
            width = height = None
        if width is not None:
            if layout is None:
                raise QuiltError(f"no layout in the name {name!r}, e.g. _qs8x6a0.75: give columns and rows")
            return {"kind": QUILT, "width": width, "height": height, "columns": layout.columns, "rows": layout.rows}
        try:
            info = probe(path, name)
        except VideoError as error:
            raise VideoError(f"cannot read {name} as an image or a video: {error}") from error
        if layout is None and screen is not None:
            step(info.width, info.height, *screen)
        return {"kind": QUILT_VIDEO if layout else HOLOGRAM_VIDEO, "width": info.width, "height": info.height,
                "columns": layout and layout.columns, "rows": layout and layout.rows, "fps": info.fps,
                "frames": info.frames, "duration": info.duration, "codec": info.codec}

    def adopt(self, path, name, details, uploaded):
        """Takes into the library a file kept otherwise, e.g. by an older version of the server: moved, not copied.
        `details` are the Item's fields but its id, name, file, size and time. Returns the item."""
        with self.lock:
            id = self._new_id()
            file = f"{id}{Path(path).suffix.lower()}"
            self.folder.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), self.folder / file)
            item = Item(id=id, name=name, file=file, size=(self.folder / file).stat().st_size, uploaded=uploaded,
                        **details)
            self.items[id] = item
            self._save()
            return item

    def remove(self, item):
        with self.lock:
            if self.items.pop(item.id, None) is not None:
                self.path(item).unlink(missing_ok=True)
                self._save()

    def _new_id(self):
        while True:
            id = secrets.token_hex(4)
            if id not in self.items:
                return id
