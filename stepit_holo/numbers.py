"""A test quilt: each view shows its number, from 1, large, on a colour of its own.

On a Looking Glass that interleaves right, one number fills the screen, and it
changes as the viewer moves sideways, in order. A mix of numbers, or a white
blur, says that the calibration, or the way it is applied, is wrong.

The digits are drawn as seven segments, with numpy: no font is needed.
"""

import colorsys

import numpy as np

from .layout import Layout

# The segments of each digit: a top, b top right, c bottom right, d bottom, e bottom left, f top left, g middle.
SEGMENTS = ["abcdef", "bc", "abdeg", "abcdg", "bcfg", "acdfg", "acdefg", "abc", "abcdefg", "abcdfg"]


def _digit(image, digit, left, top, width, height, thickness):
    """Draws a digit in black, in the box at left, top of width x height."""
    middle = top + (height - thickness) // 2
    boxes = {
        "a": (left, top, width, thickness),
        "b": (left + width - thickness, top, thickness, height // 2),
        "c": (left + width - thickness, top + height // 2, thickness, height - height // 2),
        "d": (left, top + height - thickness, width, thickness),
        "e": (left, top + height // 2, thickness, height - height // 2),
        "f": (left, top, thickness, height // 2),
        "g": (left, middle, width, thickness),
    }
    for segment in SEGMENTS[digit]:
        x, y, w, h = boxes[segment]
        image[y:y + h, x:x + w] = 0


def view(number, count, width, height):
    """One view: its number, large, on a colour of its own."""
    red, green, blue = colorsys.hsv_to_rgb((number - 1) / count, 0.6, 0.9)
    image = np.empty((height, width, 3), np.uint8)
    image[:] = (round(red * 255), round(green * 255), round(blue * 255))
    digits = [int(d) for d in str(number)]
    digit_height = height // 2
    digit_width = min(digit_height // 2, width * 2 // (3 * len(digits) + 1))
    thickness = max(2, digit_width // 5)
    gap = digit_width // 2
    total = len(digits) * digit_width + (len(digits) - 1) * gap
    left, top = (width - total) // 2, (height - digit_height) // 2
    for i, digit in enumerate(digits):
        _digit(image, digit, left + i * (digit_width + gap), top, digit_width, digit_height, thickness)
    return image


def numbers_quilt(layout=Layout(8, 6), view_width=420, view_height=560):
    """The test quilt, an RGB array, view 1 at the bottom left: by default a Portrait's, 8 x 6 views of 420 x 560."""
    quilt = np.empty((layout.rows * view_height, layout.columns * view_width, 3), np.uint8)
    for index in range(layout.views):
        row = layout.rows - 1 - index // layout.columns
        column = index % layout.columns
        quilt[row * view_height:(row + 1) * view_height, column * view_width:(column + 1) * view_width] = \
            view(index + 1, layout.views, view_width, view_height)
    return quilt
