"""The command line: stepit-holo show | render | numbers | calibration. See README.md."""

import argparse
import logging
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
from PIL import Image

from . import __version__
from .calibration import calibration_files, find_calibration, load_calibration
from .interleave import interleave
from .layout import Layout
from .numbers import numbers_quilt

# A Portrait's quilt is 11 million pixels, a large one 100 million: still a quilt, not a decompression bomb.
Image.MAX_IMAGE_PIXELS = 300_000_000


def read_quilt(path):
    try:
        with Image.open(path) as image:
            return np.asarray(image.convert("RGB"))
    except OSError as error:
        raise RuntimeError(f"cannot read the quilt {path}: {error}") from error


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


def show(hologram):
    # GTK only when something is shown: render works without a desktop.
    from .viewer import show as show_on_screen

    return show_on_screen(hologram)


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

    common(commands.add_parser("show", help="show a quilt on the Looking Glass, until Escape or q"))
    render = commands.add_parser("render", help="save the hologram of a quilt as an image, without showing it")
    common(render)
    render.add_argument("-o", "--output", type=Path, required=True, help="the hologram, e.g. hologram.png")
    numbers = commands.add_parser("numbers", help="show a test quilt of numbered views, 1 to 48")
    common(numbers, quilt=False)
    numbers.add_argument("--quilt-output", type=Path, help="save the test quilt itself, and show nothing")
    calibration = commands.add_parser("calibration", help="print the Looking Glass's calibration")
    calibration.add_argument("--calibration", type=Path, help="a visual.json, instead of the one found")

    arguments = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    try:
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
        return show(hologram)
    except (RuntimeError, ValueError) as error:
        print(f"stepit-holo: {error}", file=sys.stderr)
        return 1
