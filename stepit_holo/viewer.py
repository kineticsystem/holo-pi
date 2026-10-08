"""Shows a hologram full-screen, pixel for pixel, on the Looking Glass, with GTK.

The Looking Glass is the monitor of the calibration's size, e.g. 1536 x 2048
for a Portrait. GTK draws at 100% whatever the desktop's scaling: one pixel off,
and the hologram is drawn for the wrong lenses. Under Wayland, Raspberry Pi
OS's default, GTK makes the window fullscreen on that monitor itself; under
X11, GNOME ignores that request, and x11.fullscreen_on() asks the window
manager as a pager would.

The viewer prints "Showing ..." once its window covers the Looking Glass, and
runs until the window is closed, Escape or q is pressed, or the process is
stopped.
"""

import os
import sys

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


def show(hologram, out=sys.stdout):
    """Shows the hologram, an RGB array of the Looking Glass's size, until the window is closed. Returns 0 if
    it was shown, 1 if not."""
    if not Gtk.init_check(sys.argv)[0]:
        print("No desktop to show on: is DISPLAY or WAYLAND_DISPLAY set?", file=out, flush=True)
        return 1
    height, width = hologram.shape[:2]
    display = Gdk.Display.get_default()
    found = looking_glass_monitor(display, width, height)
    if found is None:
        sizes = ", ".join(f"{g.width} x {g.height}" for g in
                          (display.get_monitor(i).get_geometry() for i in range(display.get_n_monitors())))
        print(f"No monitor of {width} x {height}, only {sizes}. Is the Looking Glass on HDMI, switched on, "
              "and part of the desktop in its display settings, at 100%?", file=out, flush=True)
        return 1
    number, geometry = found
    x11 = type(display).__name__ == "X11Display"

    data = GLib.Bytes.new(hologram.tobytes())
    pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(data, GdkPixbuf.Colorspace.RGB, False, 8, width, height, width * 3)
    window = Gtk.Window(title="stepit-holo")
    window.add(Gtk.Image.new_from_pixbuf(pixbuf))
    window.connect("destroy", Gtk.main_quit)
    window.connect("key-press-event",
                   lambda _, event: Gtk.main_quit() if event.keyval in (Gdk.KEY_Escape, Gdk.KEY_q) else None)

    def on_map(*_):
        window.fullscreen_on_monitor(window.get_screen(), number)
        if x11:
            from .x11 import fullscreen_on
            fullscreen_on(window.get_window().get_xid(), geometry.x, geometry.y)

    window.connect("map-event", on_map)
    result = {"shown": False, "waited": 0}

    def check():
        state = window.get_window().get_state()
        covers = bool(state & Gdk.WindowState.FULLSCREEN) and \
            (window.get_allocated_width(), window.get_allocated_height()) == (width, height)
        if covers and x11:
            # Under X11 the position is known: it must be the Looking Glass's.
            covers = tuple(window.get_window().get_origin()[1:]) == (geometry.x, geometry.y)
        if covers:
            result["shown"] = True
            print(f"Showing on the monitor at {geometry.x}, {geometry.y}, {width} x {height}", file=out, flush=True)
            return False
        result["waited"] += 200
        if result["waited"] >= WAIT_MS:
            print("The window did not go full-screen on the Looking Glass", file=out, flush=True)
            Gtk.main_quit()
            return False
        return True

    window.show_all()
    window.get_window().set_cursor(Gdk.Cursor.new_for_display(display, Gdk.CursorType.BLANK_CURSOR))
    GLib.timeout_add(200, check)
    Gtk.main()
    return 0 if result["shown"] else 1
