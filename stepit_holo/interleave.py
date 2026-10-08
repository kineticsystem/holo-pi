"""Interleaving: a quilt turned into the image a Looking Glass shows, the hologram.

A Looking Glass is a screen behind a sheet of slanted lenses: each sub-pixel is
seen from one direction only. The hologram gives each sub-pixel the colour of
the view seen from its direction, at the same place in the view. For the
sub-pixel i (0 red, 1 green, 2 blue) of the pixel at u, v, from the bottom left
of the screen in fractions of it, the view is

    ((u + i * subp + v * tilt) * pitch - center) modulo 1, reversed if inverted,

times the number of views, as in Looking Glass's lenticular shader.

Which sub-pixel of the quilt each sub-pixel of the screen takes depends only on
the calibration, the layout and the quilt's size, not on the picture: the
Interleaver works it out once, as a table of 9.4 million indices for a
Portrait, keeps it on disk, and then turns a quilt into a hologram in a lookup.
"""

import hashlib
import logging
import os
from dataclasses import astuple
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

# Bumped when the table's computation changes, so that tables cached before are not used.
TABLE_VERSION = 1


def cache_folder():
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "stepit-holo"


def table(calibration, layout, quilt_width, quilt_height, reverse=False):
    """For each sub-pixel of the screen, the index of the quilt's sub-pixel it takes, in a flat RGB quilt.

    The result has the screen's shape, height x width x 3."""
    cal, views = calibration, layout.views
    # Each pixel's centre, from the bottom left, in fractions of the screen.
    u = (np.arange(cal.width) + 0.5) / cal.width
    v = 1.0 - (np.arange(cal.height) + 0.5) / cal.height
    u, v = np.meshgrid(u, v)
    dtype = np.int32 if quilt_width * quilt_height * 3 < 2**31 else np.int64
    indices = np.empty((cal.height, cal.width, 3), dtype)
    for subpixel in range(3):
        position = np.mod((u + subpixel * cal.subp + v * cal.tilt) * cal.pitch - cal.center, 1.0)
        if cal.inverted:
            position = 1.0 - position
        view = np.minimum(np.floor(position * views), views - 1)
        if reverse:
            view = views - 1 - view
        # The same place in that view, in the quilt: x from the left, y from the bottom.
        x = (np.mod(view, layout.columns) + u) / layout.columns
        y = (np.floor(view / layout.columns) + v) / layout.rows
        column = np.clip((x * quilt_width).astype(np.int64), 0, quilt_width - 1)
        row = quilt_height - 1 - np.clip((y * quilt_height).astype(np.int64), 0, quilt_height - 1)
        indices[..., subpixel] = (row * quilt_width + column) * 3 + subpixel
    return indices


class Interleaver:
    """Turns quilts of one layout and size into holograms for one Looking Glass."""

    def __init__(self, calibration, layout, quilt_width, quilt_height, reverse=False, cache=True):
        self.calibration = calibration
        self.quilt_shape = (quilt_height, quilt_width, 3)
        arguments = (calibration, layout, quilt_width, quilt_height, reverse)
        key = repr((TABLE_VERSION, astuple(calibration), astuple(layout), quilt_width, quilt_height, reverse))
        path = cache_folder() / f"table-{hashlib.sha256(key.encode()).hexdigest()[:16]}.npy"
        self.table = None
        if cache and path.exists():
            try:
                self.table = np.load(path)
            except (OSError, ValueError) as error:
                log.warning("Ignoring the cached table %s: %s", path, error)
        if self.table is None:
            self.table = table(*arguments)
            if cache:
                self._save(path)

    def _save(self, path):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp.npy")
            np.save(temporary, self.table)
            temporary.replace(path)
        except OSError as error:
            log.warning("Cannot cache the table in %s: %s", path, error)

    def __call__(self, quilt):
        """The hologram of a quilt, an RGB array of the quilt's size: an RGB array of the screen's size."""
        if quilt.shape != self.quilt_shape:
            raise ValueError(f"a quilt of {quilt.shape}, for an interleaver of {self.quilt_shape}")
        return np.ascontiguousarray(quilt).reshape(-1)[self.table]


def interleave(quilt, layout, calibration, reverse=False, cache=True):
    """The hologram of a quilt, an RGB array, for a Looking Glass."""
    height, width = quilt.shape[:2]
    return Interleaver(calibration, layout, width, height, reverse, cache)(quilt)
