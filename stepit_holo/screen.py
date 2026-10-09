"""The screens a hologram is shown on: a desktop's monitor, with GTK, or the screen itself, through DRM/KMS.

Both have the same methods: show(hologram) returns where it is shown, clear(),
close(), and run(stop), which runs on the main thread until `stop`, a
threading.Event, is set or the process is stopped.
"""

import os
import signal

KINDS = ["auto", "desktop", "drm"]


def desktop_running():
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def choose(kind="auto"):
    """The kind of screen to open: "auto" is DRM/KMS when a card has a connected screen that nothing drives, e.g.
    on a computer without a desktop, whatever DISPLAY says, e.g. over ssh -X; otherwise the desktop, if this
    process has one, and DRM/KMS again if not, whose error then says what holds the screens."""
    if kind != "auto":
        return kind
    from .drm import screen_free
    if screen_free():
        return "drm"
    return "desktop" if desktop_running() else "drm"


def open_screen(kind="auto", closable=True):
    """The screen of the given kind: "desktop", "drm", or "auto", see choose(). Call it on the main thread."""
    kind = choose(kind)
    if kind == "desktop":
        # GTK only when a desktop is used: the rest works without it.
        from .viewer import DesktopScreen
        return DesktopScreen(closable=closable)
    if kind == "drm":
        from .drm import DrmScreen
        return _Interruptible(DrmScreen())
    raise ValueError(f"no screen {kind!r}: one of {', '.join(KINDS)}")


class _Interruptible:
    """A screen whose run() also ends on SIGINT and SIGTERM, e.g. docker stop."""

    def __init__(self, screen):
        self.screen = screen
        self.name = screen.name

    def show(self, hologram):
        return self.screen.show(hologram)

    def clear(self):
        self.screen.clear()

    def close(self):
        self.screen.close()

    def run(self, stop):
        previous = {number: signal.signal(number, lambda *_: stop.set()) for number in (signal.SIGINT, signal.SIGTERM)}
        try:
            self.screen.run(stop)
        finally:
            for number, handler in previous.items():
                signal.signal(number, handler)
