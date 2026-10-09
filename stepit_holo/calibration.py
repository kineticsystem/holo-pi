"""The calibration of a Looking Glass: where its lenses are over its pixels.

Every Looking Glass is calibrated in the factory, and carries its calibration
on its own USB drive, LKG_calibration/visual.json, which the desktop mounts,
e.g. under /media/<user>/LKG-P00671 on Ubuntu and Raspberry Pi OS. The values
the interleaving needs are derived from it as Looking Glass's lenticular
shader derives them, in their WebXR library
(https://github.com/Looking-Glass/looking-glass-webxr, Apache 2.0).
"""

import json
import logging
import math
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

# Where desktops mount a USB drive: /media/<user>/<label> on Ubuntu and
# Raspberry Pi OS, /run/media/<user>/<label> on Fedora and Arch.
MOUNTS = ["/media", "/run/media"]
CALIBRATION_FILE = "LKG_calibration/visual.json"
# Without a desktop, nothing mounts the drive: mount_drives() mounts it here, by its label, e.g. LKG-P00671.
LABELS = "/dev/disk/by-label"
LABEL_PREFIX = "LKG-"
OWN_MOUNTS = "/media/stepit-holo"


@dataclass(frozen=True)
class Calibration:
    """What the interleaving needs of a Looking Glass's calibration."""

    serial: str
    width: int  # The screen, in pixels.
    height: int
    pitch: float  # Lenses across the screen's width, along their slant.
    tilt: float  # How far the lenses slant: the horizontal shift per screen height, in screen widths.
    center: float  # Where view 0 starts under a lens, as a fraction of a lens.
    subp: float  # The width of a sub-pixel, as a fraction of the screen's width.
    inverted: bool  # The views go from right to left under each lens.

    @classmethod
    def from_visual(cls, values):
        """From the contents of visual.json, where each value is a number or {"value": number}."""
        v = {key: value["value"] if isinstance(value, dict) else value for key, value in values.items()}
        width, height = int(v["screenW"]), int(v["screenH"])
        # A mirrored screen: the lenses slant, and the sub-pixels go, the other way.
        flip = -1.0 if v.get("flipImageX", 0) else 1.0
        return cls(
            serial=str(v.get("serial", "")),
            width=width,
            height=height,
            pitch=v["pitch"] * width / v["DPI"] * math.cos(math.atan(1.0 / v["slope"])),
            tilt=height / (width * v["slope"]) * flip,
            center=v["center"],
            subp=flip / (width * 3),
            inverted=bool(v.get("invView", 1)),
        )


def load_calibration(path):
    """The calibration in a visual.json file."""
    try:
        return Calibration.from_visual(json.loads(Path(path).read_text()))
    except (OSError, ValueError, KeyError) as error:
        raise RuntimeError(f"cannot read the calibration {path}: {error}") from error


def calibration_files(mounts=MOUNTS):
    """The visual.json files of the Looking Glasses whose drives are mounted."""
    return sorted(path for mount in mounts for path in Path(mount).glob(f"*/*/{CALIBRATION_FILE}"))


def find_calibration(mounts=MOUNTS):
    """The calibration of the Looking Glass whose drive is mounted: the first one if there are several."""
    paths = calibration_files(mounts)
    if not paths:
        places = " or ".join(f"{mount}/*/*/{CALIBRATION_FILE}" for mount in mounts)
        raise RuntimeError(f"no Looking Glass found: no {places}. Is its USB cable plugged in, "
                           "with a cable that carries data?")
    return load_calibration(paths[0])


_failures = set()


def _mounted_devices():
    try:
        lines = Path("/proc/mounts").read_text().splitlines()
    except OSError:
        return set()
    return {os.path.realpath(line.split()[0]) for line in lines if line.startswith("/dev/")}


def mount_drives(labels=LABELS, target=OWN_MOUNTS):
    """Mounts, read-only, under target/<label>, the drives of the Looking Glasses that nothing has mounted, e.g.
    on a computer without a desktop. Needs root, e.g. in a container. Returns the folders it mounted."""
    mounted, folders = _mounted_devices(), []
    for link in sorted(Path(labels).glob(f"{LABEL_PREFIX}*")):
        device = os.path.realpath(link)
        if device in mounted:
            continue
        folder = Path(target, link.name)
        try:
            folder.mkdir(parents=True, exist_ok=True)
            subprocess.run(["mount", "-o", "ro,nosuid,nodev,noexec", device, str(folder)], check=True,
                           capture_output=True, text=True)
        except (OSError, subprocess.CalledProcessError) as error:
            message = f"Cannot mount {device} on {folder}: {(getattr(error, 'stderr', '') or str(error)).strip()}"
            if message not in _failures:  # Once, not at every retry.
                _failures.add(message)
                log.warning(message)
            continue
        log.info("Mounted %s, the drive of %s, on %s", device, link.name, folder)
        folders.append(folder)
    return folders
