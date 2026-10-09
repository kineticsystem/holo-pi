"""Shows a hologram full-screen, pixel for pixel, on the Looking Glass, with GTK, on a desktop.

The Looking Glass is the monitor of the hologram's size, e.g. 1536 x 2048 for a
Portrait. GTK draws at 100% whatever the desktop's scaling: one pixel off, and
the hologram is drawn for the wrong lenses. Under Wayland, GTK makes the window
fullscreen on that monitor itself; under X11, GNOME ignores that request, and
x11.fullscreen_on() asks the window manager as a pager would.

GTK runs on the main thread, in run(); show() is called from another thread,
and returns once the window covers the Looking Glass. A new hologram replaces
the one in the window.
"""

import os
import signal
import sys
import threading

# Before GTK is loaded: GTK reads them once.
os.environ["GDK_SCALE"] = "1"
os.environ["GDK_DPI_SCALE"] = "1"

import gi  # noqa: E402

gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

WAIT_MS = 10000


def looking_glass_monitor(display, width, height):
    """The number and geometry of the monitor of the given size, or None."""
    for number in range(display.get_n_monitors()):
        geometry = display.get_monitor(number).get_geometry()
        if (geometry.width, geometry.height) == (width, height):
            return number, geometry
    return None


class DesktopScreen:
    """The Looking Glass, as a monitor of the desktop. `closable`: closing the window, or Escape or q, ends
    run(), as for the command line; otherwise it only closes the window, until the next show()."""

    name = "desktop"

    def __init__(self, closable=True):
        if not Gtk.init_check(sys.argv)[0]:
            raise RuntimeError("no desktop to show on: is DISPLAY or WAYLAND_DISPLAY set?")
        self.display = Gdk.Display.get_default()
        self.closable = closable
        self.window = None
        self.image = None
        self.shown_on = None  # The geometry of the monitor the window covers, and where that is.

    def show(self, hologram):
        """Shows an RGB hologram, from a thread other than GTK's. Returns where; raises RuntimeError if it
        cannot."""
        done, result = threading.Event(), {}
        GLib.idle_add(self._show, hologram, done, result)
        if not done.wait(WAIT_MS / 1000 + 5):
            raise RuntimeError("the desktop did not answer")
        if "error" in result:
            raise RuntimeError(result["error"])
        return result["where"]

    def clear(self):
        """Closes the window, if it is open."""
        GLib.idle_add(self._close_window)

    def close(self):
        self._close_window()

    def run(self, stop):
        """Runs GTK until `stop`, a threading.Event, is set, the process is interrupted or terminated, or,
        if closable, the window is closed."""
        def quit_now(*_):
            stop.set()
            Gtk.main_quit()
            return GLib.SOURCE_REMOVE

        for number in (signal.SIGINT, signal.SIGTERM):
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, number, quit_now)
        GLib.timeout_add(200, lambda: quit_now() if stop.is_set() else GLib.SOURCE_CONTINUE)
        Gtk.main()

    def _close_window(self):
        if self.window is not None:
            window, self.window, self.image, self.shown_on = self.window, None, None, None
            window.destroy()
        return GLib.SOURCE_REMOVE

    def _closed_by_user(self, *_):
        if self.closable:
            Gtk.main_quit()
        else:
            self._close_window()

    def _show(self, hologram, done, result):
        height, width = hologram.shape[:2]
        found = looking_glass_monitor(self.display, width, height)
        if found is None:
            sizes = ", ".join(f"{g.width} x {g.height}" for g in (self.display.get_monitor(i).get_geometry()
                                                                  for i in range(self.display.get_n_monitors())))
            result["error"] = (f"no monitor of {width} x {height}, only {sizes}. Is the Looking Glass on HDMI, "
                               "switched on, and part of the desktop in its display settings, at 100%?")
            done.set()
            return GLib.SOURCE_REMOVE
        number, geometry = found
        data = GLib.Bytes.new(hologram.tobytes())
        pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(data, GdkPixbuf.Colorspace.RGB, False, 8, width, height, width * 3)
        key = (geometry.x, geometry.y, width, height)
        if self.window is not None and self.shown_on and self.shown_on[0] == key:
            # The window already covers the Looking Glass: only the picture changes.
            self.image.set_from_pixbuf(pixbuf)
            result["where"] = self.shown_on[1]
            done.set()
            return GLib.SOURCE_REMOVE
        self._close_window()
        self._open_window(pixbuf, number, geometry, key, done, result)
        return GLib.SOURCE_REMOVE

    def _open_window(self, pixbuf, number, geometry, key, done, result):
        width, height = key[2], key[3]
        x11 = type(self.display).__name__ == "X11Display"
        window = Gtk.Window(title="holo-pi")
        image = Gtk.Image.new_from_pixbuf(pixbuf)
        window.add(image)
        window.connect("delete-event", lambda *_: self._closed_by_user() or True)
        window.connect("key-press-event", lambda _, event: self._closed_by_user()
                       if event.keyval in (Gdk.KEY_Escape, Gdk.KEY_q) else None)

        def on_map(*_):
            window.fullscreen_on_monitor(window.get_screen(), number)
            if x11:
                from .x11 import fullscreen_on
                fullscreen_on(window.get_window().get_xid(), geometry.x, geometry.y)

        window.connect("map-event", on_map)
        self.window, self.image = window, image
        waited = {"ms": 0}

        def check():
            if self.window is not window:
                result["error"] = "the window was closed before it covered the Looking Glass"
                done.set()
                return GLib.SOURCE_REMOVE
            state = window.get_window().get_state()
            covers = bool(state & Gdk.WindowState.FULLSCREEN) and \
                (window.get_allocated_width(), window.get_allocated_height()) == (width, height)
            if covers and x11:
                # Under X11 the position is known: it must be the Looking Glass's.
                covers = tuple(window.get_window().get_origin()[1:]) == (geometry.x, geometry.y)
            if covers:
                where = f"the monitor at {geometry.x}, {geometry.y}, {width} x {height}"
                self.shown_on = (key, where)
                result["where"] = where
                done.set()
                return GLib.SOURCE_REMOVE
            waited["ms"] += 200
            if waited["ms"] >= WAIT_MS:
                self._close_window()
                result["error"] = "the window did not go full-screen on the Looking Glass"
                done.set()
                return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE

        window.show_all()
        window.get_window().set_cursor(Gdk.Cursor.new_for_display(self.display, Gdk.CursorType.BLANK_CURSOR))
        GLib.timeout_add(200, check)
