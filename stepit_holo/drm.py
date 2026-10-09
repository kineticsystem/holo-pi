"""Shows a hologram full-screen on the Looking Glass without a desktop, through DRM/KMS, with libdrm and ctypes.

On a computer with no desktop, e.g. a Raspberry Pi with Raspberry Pi OS Lite,
nothing else drives the screens, and a program may set their modes and show its
own image on them, as a desktop does. The Looking Glass is the connected screen
whose mode is of the calibration's size, e.g. 1536 x 2048 for a Portrait, its
preferred mode. The hologram goes into a dumb buffer, an image in memory that
the display controller scans out pixel for pixel: no scaling, no window, no
compositor.

The screen shows the hologram for as long as the program keeps the card open.
When it closes it, e.g. when it stops, the console comes back.

A desktop that runs on the same card holds it, its DRM master, and a program
cannot then set a mode: open_screen() uses the desktop's own window instead,
see viewer.py.
"""

import ctypes
import ctypes.util
import errno
import mmap
import os
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np

CARDS = "/dev/dri"
CONNECTED = 1
PREFERRED = 1 << 3  # DRM_MODE_TYPE_PREFERRED: the mode the screen asks for.

# The names of the connector types of the kernel's drm_mode.h, for the messages.
CONNECTOR_TYPES = {1: "VGA", 2: "DVI-I", 3: "DVI-D", 4: "DVI-A", 5: "Composite", 6: "S-Video", 7: "LVDS",
                   8: "Component", 9: "DIN", 10: "DP", 11: "HDMI-A", 12: "HDMI-B", 13: "TV", 14: "eDP",
                   15: "Virtual", 16: "DSI", 17: "DPI", 18: "Writeback", 19: "SPI", 20: "USB"}


class _ModeInfo(ctypes.Structure):
    _fields_ = [("clock", ctypes.c_uint32),
                ("hdisplay", ctypes.c_uint16), ("hsync_start", ctypes.c_uint16), ("hsync_end", ctypes.c_uint16),
                ("htotal", ctypes.c_uint16), ("hskew", ctypes.c_uint16),
                ("vdisplay", ctypes.c_uint16), ("vsync_start", ctypes.c_uint16), ("vsync_end", ctypes.c_uint16),
                ("vtotal", ctypes.c_uint16), ("vscan", ctypes.c_uint16),
                ("vrefresh", ctypes.c_uint32), ("flags", ctypes.c_uint32), ("type", ctypes.c_uint32),
                ("name", ctypes.c_char * 32)]


class _Resources(ctypes.Structure):
    _fields_ = [("count_fbs", ctypes.c_int), ("fbs", ctypes.POINTER(ctypes.c_uint32)),
                ("count_crtcs", ctypes.c_int), ("crtcs", ctypes.POINTER(ctypes.c_uint32)),
                ("count_connectors", ctypes.c_int), ("connectors", ctypes.POINTER(ctypes.c_uint32)),
                ("count_encoders", ctypes.c_int), ("encoders", ctypes.POINTER(ctypes.c_uint32)),
                ("min_width", ctypes.c_uint32), ("max_width", ctypes.c_uint32),
                ("min_height", ctypes.c_uint32), ("max_height", ctypes.c_uint32)]


class _Connector(ctypes.Structure):
    _fields_ = [("connector_id", ctypes.c_uint32), ("encoder_id", ctypes.c_uint32),
                ("connector_type", ctypes.c_uint32), ("connector_type_id", ctypes.c_uint32),
                ("connection", ctypes.c_int), ("mmWidth", ctypes.c_uint32), ("mmHeight", ctypes.c_uint32),
                ("subpixel", ctypes.c_int),
                ("count_modes", ctypes.c_int), ("modes", ctypes.POINTER(_ModeInfo)),
                ("count_props", ctypes.c_int), ("props", ctypes.POINTER(ctypes.c_uint32)),
                ("prop_values", ctypes.POINTER(ctypes.c_uint64)),
                ("count_encoders", ctypes.c_int), ("encoders", ctypes.POINTER(ctypes.c_uint32))]


class _Encoder(ctypes.Structure):
    _fields_ = [("encoder_id", ctypes.c_uint32), ("encoder_type", ctypes.c_uint32), ("crtc_id", ctypes.c_uint32),
                ("possible_crtcs", ctypes.c_uint32), ("possible_clones", ctypes.c_uint32)]


class _Crtc(ctypes.Structure):
    _fields_ = [("crtc_id", ctypes.c_uint32), ("buffer_id", ctypes.c_uint32),
                ("x", ctypes.c_uint32), ("y", ctypes.c_uint32), ("width", ctypes.c_uint32),
                ("height", ctypes.c_uint32), ("mode_valid", ctypes.c_int), ("mode", _ModeInfo),
                ("gamma_size", ctypes.c_int)]


class _CreateDumb(ctypes.Structure):
    _fields_ = [("height", ctypes.c_uint32), ("width", ctypes.c_uint32), ("bpp", ctypes.c_uint32),
                ("flags", ctypes.c_uint32), ("handle", ctypes.c_uint32), ("pitch", ctypes.c_uint32),
                ("size", ctypes.c_uint64)]


class _MapDumb(ctypes.Structure):
    _fields_ = [("handle", ctypes.c_uint32), ("pad", ctypes.c_uint32), ("offset", ctypes.c_uint64)]


class _DestroyDumb(ctypes.Structure):
    _fields_ = [("handle", ctypes.c_uint32)]


def _iowr(number, structure):
    """DRM_IOWR of the kernel's drm.h: an ioctl that reads and writes `structure`."""
    return (3 << 30) | (ctypes.sizeof(structure) << 16) | (ord("d") << 8) | number


CREATE_DUMB = _iowr(0xB2, _CreateDumb)
MAP_DUMB = _iowr(0xB3, _MapDumb)
DESTROY_DUMB = _iowr(0xB4, _DestroyDumb)

_libdrm = None


def _library():
    global _libdrm
    if _libdrm is None:
        name = ctypes.util.find_library("drm") or "libdrm.so.2"
        try:
            drm = ctypes.CDLL(name, use_errno=True)
        except OSError as error:
            raise RuntimeError(f"cannot load libdrm, {name}: install libdrm2") from error
        drm.drmModeGetResources.restype = ctypes.POINTER(_Resources)
        drm.drmModeGetResources.argtypes = [ctypes.c_int]
        drm.drmModeFreeResources.argtypes = [ctypes.POINTER(_Resources)]
        drm.drmModeGetConnector.restype = ctypes.POINTER(_Connector)
        drm.drmModeGetConnector.argtypes = [ctypes.c_int, ctypes.c_uint32]
        drm.drmModeFreeConnector.argtypes = [ctypes.POINTER(_Connector)]
        drm.drmModeGetEncoder.restype = ctypes.POINTER(_Encoder)
        drm.drmModeGetEncoder.argtypes = [ctypes.c_int, ctypes.c_uint32]
        drm.drmModeFreeEncoder.argtypes = [ctypes.POINTER(_Encoder)]
        drm.drmModeGetCrtc.restype = ctypes.POINTER(_Crtc)
        drm.drmModeGetCrtc.argtypes = [ctypes.c_int, ctypes.c_uint32]
        drm.drmModeFreeCrtc.argtypes = [ctypes.POINTER(_Crtc)]
        drm.drmModeAddFB.argtypes = [ctypes.c_int, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint8,
                                     ctypes.c_uint8, ctypes.c_uint32, ctypes.c_uint32,
                                     ctypes.POINTER(ctypes.c_uint32)]
        drm.drmModeRmFB.argtypes = [ctypes.c_int, ctypes.c_uint32]
        drm.drmModeSetCrtc.argtypes = [ctypes.c_int, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32,
                                       ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32), ctypes.c_int,
                                       ctypes.POINTER(_ModeInfo)]
        drm.drmIoctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_void_p]
        drm.drmAuthMagic.argtypes = [ctypes.c_int, ctypes.c_uint]
        _libdrm = drm
    return _libdrm


def _check(result, what):
    if result != 0:
        number = ctypes.get_errno() or (-result if result < 0 else 0)
        raise OSError(number, f"{what}: {os.strerror(number)}")


@dataclass
class Output:
    """A connected screen of a card, and the mode to show on it."""

    card: str
    connector: int  # The connector's id.
    name: str  # e.g. HDMI-A-1.
    crtc: int  # The display controller that drives it.
    mode: _ModeInfo

    @property
    def size(self):
        return self.mode.hdisplay, self.mode.vdisplay


def choose_mode(modes, width, height):
    """The mode of width x height among `modes`, the preferred one first, then the highest refresh, or None."""
    fitting = [mode for mode in modes if (mode.hdisplay, mode.vdisplay) == (width, height)]
    fitting.sort(key=lambda mode: (bool(mode.type & PREFERRED), mode.vrefresh), reverse=True)
    return fitting[0] if fitting else None


def _connector_name(connector):
    return f"{CONNECTOR_TYPES.get(connector.connector_type, 'Unknown')}-{connector.connector_type_id}"


def _crtc_for(drm, fd, resources, connector, taken):
    """The display controller to drive the connector: the one that drives it now, or a free one it can use."""
    if connector.encoder_id:
        encoder = drm.drmModeGetEncoder(fd, connector.encoder_id)
        if encoder:
            crtc = encoder.contents.crtc_id
            drm.drmModeFreeEncoder(encoder)
            if crtc and crtc not in taken:
                return crtc
    for e in range(connector.count_encoders):
        encoder = drm.drmModeGetEncoder(fd, connector.encoders[e])
        if not encoder:
            continue
        possible = encoder.contents.possible_crtcs
        drm.drmModeFreeEncoder(encoder)
        for c in range(resources.count_crtcs):
            if possible & (1 << c) and resources.crtcs[c] not in taken:
                return resources.crtcs[c]
    return None


def screens(fd, card):
    """The connected screens of an open card: (Output with mode None, every mode) for each."""
    drm = _library()
    resources_pointer = drm.drmModeGetResources(fd)
    if not resources_pointer:
        return []  # A card that renders only, e.g. the Raspberry Pi 5's v3d: no screens.
    found, taken = [], set()
    try:
        resources = resources_pointer.contents
        for i in range(resources.count_connectors):
            pointer = drm.drmModeGetConnector(fd, resources.connectors[i])
            if not pointer:
                continue
            try:
                connector = pointer.contents
                if connector.connection != CONNECTED or connector.count_modes == 0:
                    continue
                modes = [_ModeInfo.from_buffer_copy(connector.modes[m]) for m in range(connector.count_modes)]
                crtc = _crtc_for(drm, fd, resources, connector, taken)
                if crtc is None:
                    continue
                taken.add(crtc)
                found.append((Output(card, connector.connector_id, _connector_name(connector), crtc, None), modes))
            finally:
                drm.drmModeFreeConnector(pointer)
    finally:
        drm.drmModeFreeResources(resources_pointer)
    return found


def cards(folder=CARDS):
    return sorted(str(path) for path in Path(folder).glob("card*"))


def _is_master(drm, fd):
    """Whether this process is the card's master, and may set the mode of its screens: drmIsMaster() of libdrm,
    which asks to authenticate a client, something only the master may do."""
    return drm.drmAuthMagic(fd, 0) != -errno.EACCES


def screen_free(folder=CARDS):
    """Whether a card has a connected screen that no other program drives, e.g. no desktop: this process could set
    its mode. The first process to open a card that has no master becomes its master, until it closes it."""
    try:
        drm = _library()
    except RuntimeError:
        return False
    for path in cards(folder):
        try:
            fd = os.open(path, os.O_RDWR | os.O_CLOEXEC)
        except OSError:
            continue  # e.g. not in the group video.
        try:
            if _is_master(drm, fd) and screens(fd, path):
                return True
        finally:
            os.close(fd)
    return False


def describe(modes):
    sizes = sorted({(mode.hdisplay, mode.vdisplay) for mode in modes}, reverse=True)
    return ", ".join(f"{w} x {h}" for w, h in sizes[:4])


def find_output(width, height, folder=CARDS):
    """Opens the card with a connected screen of width x height. Returns (fd, Output); raises RuntimeError with
    what it saw otherwise."""
    seen = []
    paths = cards(folder)
    if not paths:
        raise RuntimeError(f"no graphics card in {folder}: in a container, give it the host's /dev")
    for path in paths:
        try:
            fd = os.open(path, os.O_RDWR | os.O_CLOEXEC)
        except OSError as error:
            seen.append(f"{path}: {error.strerror}")
            continue
        try:
            for output, modes in screens(fd, path):
                mode = choose_mode(modes, width, height)
                if mode is not None:
                    output.mode = mode
                    return fd, output
                seen.append(f"{output.name} of {path}: {describe(modes)}")
        except BaseException:
            os.close(fd)
            raise
        os.close(fd)
    what = "; ".join(seen) if seen else "no screen connected"
    raise RuntimeError(f"no screen of {width} x {height}: {what}. Is the Looking Glass on HDMI and switched on?")


def xrgb(hologram):
    """An RGB hologram as XRGB8888, the pixel format every display controller scans out: blue, green, red, then
    a padding byte, in memory."""
    height, width = hologram.shape[:2]
    pixels = np.empty((height, width, 4), np.uint8)
    pixels[..., 0] = hologram[..., 2]
    pixels[..., 1] = hologram[..., 1]
    pixels[..., 2] = hologram[..., 0]
    pixels[..., 3] = 255
    return pixels


class _Buffer:
    """A dumb buffer of the screen's size, mapped into memory, and the framebuffer that shows it."""

    def __init__(self, drm, fd, width, height):
        self.drm, self.fd = drm, fd
        create = _CreateDumb(height=height, width=width, bpp=32)
        _check(drm.drmIoctl(fd, CREATE_DUMB, ctypes.byref(create)), "cannot create a buffer")
        self.handle, self.pitch, self.size = create.handle, create.pitch, create.size
        self.framebuffer = None
        self.memory = None
        try:
            framebuffer = ctypes.c_uint32()
            _check(drm.drmModeAddFB(fd, width, height, 24, 32, self.pitch, self.handle, ctypes.byref(framebuffer)),
                   "cannot add a framebuffer")
            self.framebuffer = framebuffer.value
            mapping = _MapDumb(handle=self.handle)
            _check(drm.drmIoctl(fd, MAP_DUMB, ctypes.byref(mapping)), "cannot map a buffer")
            self.memory = mmap.mmap(fd, self.size, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE,
                                    offset=mapping.offset)
        except BaseException:
            self.close()
            raise
        # The rows are `pitch` bytes apart, which may be more than width x 4.
        rows = np.frombuffer(self.memory, np.uint8, count=height * self.pitch).reshape(height, self.pitch)
        self.pixels = rows[:, :width * 4].reshape(height, width, 4)

    def close(self):
        self.pixels = None
        if self.memory is not None:
            try:
                self.memory.close()
            except BufferError:
                pass  # A view of it is still alive: the kernel frees it with the process.
            self.memory = None
        if self.framebuffer is not None:
            self.drm.drmModeRmFB(self.fd, self.framebuffer)
            self.framebuffer = None
        self.drm.drmIoctl(self.fd, DESTROY_DUMB, ctypes.byref(_DestroyDumb(handle=self.handle)))


class DrmScreen:
    """The Looking Glass, through DRM/KMS: show() puts a hologram on the connected screen of its size, and it
    stays there until the next one or close(). Thread-safe."""

    name = "drm"

    def __init__(self, folder=CARDS):
        self.folder = folder
        self.drm = _library()
        self.lock = threading.Lock()
        self.fd = None
        self.output = None
        self.buffers = []
        self.front = None
        self.saved = None  # What the display controller showed before, e.g. the console, to give it back.

    def _open(self, width, height):
        self.fd, self.output = find_output(width, height, self.folder)
        self.saved = self.drm.drmModeGetCrtc(self.fd, self.output.crtc)
        self.buffers = [_Buffer(self.drm, self.fd, width, height) for _ in range(2)]

    def _release(self):
        # What it showed before first: removing a framebuffer on screen switches the screen off.
        if self.saved:
            crtc = self.saved.contents
            if crtc.buffer_id and crtc.mode_valid:
                connector = ctypes.c_uint32(self.output.connector)
                self.drm.drmModeSetCrtc(self.fd, crtc.crtc_id, crtc.buffer_id, crtc.x, crtc.y,
                                        ctypes.byref(connector), 1, ctypes.byref(crtc.mode))
            self.drm.drmModeFreeCrtc(self.saved)
            self.saved = None
        for buffer in self.buffers:
            buffer.close()
        self.buffers, self.front = [], None
        if self.fd is not None:
            os.close(self.fd)
            self.fd, self.output = None, None

    def show(self, hologram):
        """Shows an RGB hologram on the screen of its size. Returns where; raises RuntimeError if it cannot."""
        height, width = hologram.shape[:2]
        with self.lock:
            if self.output is not None and self.output.size != (width, height):
                self._release()
            for attempt in range(2):
                try:
                    if self.fd is None:
                        self._open(width, height)
                    # Draw into the buffer not on screen, then switch: the screen never shows half of each.
                    back = self.buffers[1] if self.front is self.buffers[0] else self.buffers[0]
                    back.pixels[:] = xrgb(hologram)
                    connector = ctypes.c_uint32(self.output.connector)
                    _check(self.drm.drmModeSetCrtc(self.fd, self.output.crtc, back.framebuffer, 0, 0,
                                                   ctypes.byref(connector), 1, ctypes.byref(self.output.mode)),
                           "cannot show on the screen")
                    self.front = back
                    return f"{self.output.name} of {self.output.card}, {width} x {height}"
                except OSError as error:
                    self._release()
                    if error.errno in (errno.EACCES, errno.EPERM):
                        raise RuntimeError(f"{error}: another program drives the screens, e.g. a desktop, "
                                           "or this user may not open them, e.g. not in the group video") from error
                    # The screen may have been unplugged and plugged in again: look for it once more.
                    if attempt:
                        raise RuntimeError(str(error)) from error
                except RuntimeError:
                    self._release()
                    raise
        raise AssertionError("unreachable")

    def clear(self):
        """Shows black, if anything is shown."""
        with self.lock:
            size = self.output.size if self.output is not None else None
        if size is not None:
            self.show(np.zeros((size[1], size[0], 3), np.uint8))

    def close(self):
        """Gives the screen back, e.g. to the console."""
        with self.lock:
            self._release()

    def run(self, stop):
        """Waits until `stop`, a threading.Event, is set: the screen needs no loop of its own."""
        # In short waits, so that a signal handler that sets it is seen at once.
        while not stop.wait(0.5):
            pass
