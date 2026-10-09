"""The command line: stepit-holo show | render | numbers | calibration | serve. See README.md."""

import argparse
import logging
import sys
import threading
from dataclasses import asdict
from pathlib import Path

from PIL import Image

from . import __version__
from .calibration import calibration_files, find_calibration, load_calibration
from .interleave import interleave
from .layout import Layout
from .numbers import numbers_quilt
from .quilt import read_quilt
from .screen import KINDS, open_screen

DEFAULT_PORT = 8095


def layout_of(path, arguments):
    if arguments.columns and arguments.rows:
        return Layout(arguments.columns, arguments.rows)
    layout = Layout.from_name(path)
    if layout is None:
        raise RuntimeError(f"no layout in the name {Path(path).name}, e.g. _qs8x6a0.75: give --columns and --rows")
    return layout


def calibration_of(arguments):
    return load_calibration(arguments.calibration) if arguments.calibration else find_calibration()


def hologram_of(arguments):
    if arguments.command == "numbers":
        quilt, layout = numbers_quilt(), Layout(8, 6)
    else:
        quilt, layout = read_quilt(arguments.quilt), layout_of(arguments.quilt, arguments)
    return interleave(quilt, layout, calibration_of(arguments), reverse=arguments.reverse)


def save(image, path):
    Image.fromarray(image).save(path)
    print(f"Saved {path}")


def show(hologram, kind):
    """Shows the hologram until the window is closed, or the process is interrupted or terminated. Returns 0 if
    it was shown, 1 if not."""
    screen = open_screen(kind)
    stop, shown = threading.Event(), threading.Event()

    def put_on_screen():
        try:
            print(f"Showing on {screen.show(hologram)}", flush=True)
            shown.set()
        except RuntimeError as error:
            print(f"stepit-holo: {error}", file=sys.stderr, flush=True)
            stop.set()

    # The screen's loop runs on the main thread, GTK's for a desktop: show() waits for it from another one.
    threading.Thread(target=put_on_screen, daemon=True).start()
    try:
        screen.run(stop)
    finally:
        screen.close()
    return 0 if shown.is_set() else 1


def serve(arguments):
    try:
        from .server import serve as run_server
    except ImportError as error:
        raise RuntimeError(f"the server needs FastAPI, uvicorn and python-multipart: {error}") from error
    return run_server(host=arguments.host, port=arguments.port, screen=arguments.screen,
                      calibration=arguments.calibration, state=arguments.state, mount=arguments.mount_drive)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="stepit-holo", description="Show quilts on a Looking Glass Portrait, as holograms.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    def common(command, quilt=True):
        if quilt:
            command.add_argument("quilt", type=Path, help="the quilt, e.g. wasp_qs8x6a0.75.jpg")
            command.add_argument("--columns", type=int, help="the quilt's columns, if its name does not say")
            command.add_argument("--rows", type=int, help="the quilt's rows, if its name does not say")
        command.add_argument("--calibration", type=Path,
                             help="a visual.json, instead of the one on the Looking Glass's drive")
        command.add_argument("--reverse", action="store_true",
                             help="the views in the other order, if the depth looks inside out")

    def screen(command):
        command.add_argument("--screen", choices=KINDS, default="auto",
                             help="a desktop's monitor, or the screen itself through DRM/KMS without a desktop; "
                                  "auto: the screen itself if nothing drives it, the desktop otherwise")

    show_command = commands.add_parser("show", help="show a quilt on the Looking Glass, until Escape or q")
    common(show_command)
    screen(show_command)
    render = commands.add_parser("render", help="save the hologram of a quilt as an image, without showing it")
    common(render)
    render.add_argument("-o", "--output", type=Path, required=True, help="the hologram, e.g. hologram.png")
    numbers = commands.add_parser("numbers", help="show a test quilt of numbered views, 1 to 48")
    common(numbers, quilt=False)
    numbers.add_argument("--quilt-output", type=Path, help="save the test quilt itself, and show nothing")
    screen(numbers)
    server = commands.add_parser("serve", help="show the quilts that other computers upload, over HTTP")
    server.add_argument("--host", default="0.0.0.0", help="the address to listen on; default: every one")
    server.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"default: {DEFAULT_PORT}")
    server.add_argument("--calibration", type=Path,
                        help="a visual.json, instead of the one on the Looking Glass's drive")
    server.add_argument("--state", type=Path,
                        help="where to keep the last quilt, to show it again after a restart; "
                             "default: ~/.local/state/stepit-holo")
    server.add_argument("--mount-drive", action="store_true",
                        help="mount the Looking Glass's drive, read-only, if nothing has, e.g. without a desktop; "
                             "needs root")
    screen(server)
    calibration = commands.add_parser("calibration", help="print the Looking Glass's calibration")
    calibration.add_argument("--calibration", type=Path, help="a visual.json, instead of the one found")

    arguments = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    try:
        if arguments.command == "serve":
            return serve(arguments)
        if arguments.command == "calibration":
            if not arguments.calibration:
                for path in calibration_files():
                    print(f"Found {path}")
            for key, value in asdict(calibration_of(arguments)).items():
                print(f"{key}: {value}")
            return 0
        if arguments.command == "numbers" and arguments.quilt_output:
            save(numbers_quilt(), arguments.quilt_output)
            return 0
        hologram = hologram_of(arguments)
        if arguments.command == "render":
            save(hologram, arguments.output)
            return 0
        return show(hologram, arguments.screen)
    except (RuntimeError, ValueError) as error:
        print(f"stepit-holo: {error}", file=sys.stderr)
        return 1
