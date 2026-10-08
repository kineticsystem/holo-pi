# StepIt Holo

## Table of Contents <!-- omit in toc -->

- [Introduction](#introduction)
- [Try It](#try-it)
- [Prerequisites](#prerequisites)
- [Install StepIt Holo](#install-stepit-holo)
  - [Check out the Git Repository](#check-out-the-git-repository)
  - [Install the Command](#install-the-command)
- [Running the Application](#running-the-application)
  - [Show a Quilt](#show-a-quilt)
  - [Check the Looking Glass with Numbered Views](#check-the-looking-glass-with-numbered-views)
  - [Save a Hologram](#save-a-hologram)
  - [See the Calibration](#see-the-calibration)
- [Use It as a Library](#use-it-as-a-library)
- [Tests](#tests)
- [Troubleshooting](#troubleshooting)
- [Licences](#licences)

## Introduction

StepIt Holo shows quilts on a Looking Glass display as holograms, without Looking Glass's software. It runs on Ubuntu and on Raspberry Pi OS, with Python, numpy, Pillow and GTK.

A quilt is the format of Looking Glass's still holograms: one image holding a grid of views of a scene, each seen from a slightly different direction, e.g. 48 views in 8 columns and 6 rows for the Looking Glass Portrait. StepIt Holo:

- reads the display's calibration from the display itself: every Looking Glass carries it on its own USB drive;
- interleaves the quilt into the image the display must show, so that each eye sees the right view through the display's lenses;
- shows that image full-screen on the Looking Glass, pixel for pixel, whatever monitor the desktop puts new windows on.

It works with any quilt, from any software that makes them. It was made with a Looking Glass Portrait; other models should work, see [Troubleshooting](#troubleshooting).

## Try It

The repo holds a sample quilt for the Looking Glass Portrait, [`quilts/wasp_qs8x6a0.75.jpg`](quilts/wasp_qs8x6a0.75.jpg): a wasp, a macro photograph taken from 48 angles, 8 x 6 views of 420 x 560. With the [prerequisites](#prerequisites) in place, it takes three commands to see it in 3D:

```bash
git clone https://github.com/kineticsystem/stepit-holo.git
cd stepit-holo
./stepit-holo show quilts/wasp_qs8x6a0.75.jpg
```

Through the lenses, the wasp stands in front of a white background, and turns as you move your head sideways. Press Escape or `q` on its window to close it.

## Prerequisites

- **Ubuntu 24.04 or Raspberry Pi OS (Bookworm),** with a desktop: GNOME on X11 or on Wayland, or Raspberry Pi OS's own, on Wayland. Other Linux desktops should work.
- **Python 3.11 or later, numpy, Pillow and GTK 3's Python bindings,** all from the system's packages:

  ```bash
  sudo apt install python3-numpy python3-pil python3-gi gir1.2-gtk-3.0
  ```

- **A Looking Glass,** on HDMI and on USB to the same computer. The USB cable must carry data, not only power: through it, the desktop mounts the display's drive, e.g. `/media/<user>/LKG-P00671`, with its calibration. In the display settings, the Looking Glass is part of the desktop ("Join Displays"), in its own orientation. StepIt Holo draws at 100% whatever the desktop's scaling, so a whole factor, e.g. 200% on a 4K desktop, works too; a fractional one, e.g. 150%, does not under X11, where GNOME scales the whole screen image.

> [!IMPORTANT]
> No Looking Glass software is needed, and none may run on the Looking Glass at the same time: Looking Glass Bridge would draw over StepIt Holo's window.

## Install StepIt Holo

### Check out the Git Repository

```bash
git clone https://github.com/kineticsystem/stepit-holo.git
cd stepit-holo
```

The command runs from the checkout as it is, with no installation:

```bash
./stepit-holo show quilts/wasp_qs8x6a0.75.jpg
```

### Install the Command

To have `stepit-holo` on the `PATH`, install it with pipx, which both Ubuntu and Raspberry Pi OS package. `--system-site-packages` lets it use the system's numpy, Pillow and GTK bindings:

```bash
sudo apt install pipx
pipx install --system-site-packages git+https://github.com/kineticsystem/stepit-holo.git
```

## Running the Application

### Show a Quilt

```bash
./stepit-holo show quilts/wasp_qs8x6a0.75.jpg
```

The hologram fills the Looking Glass until you press Escape or `q` on its window, or stop the command. The command says `Showing on the monitor at ...` once the window covers the Looking Glass.

The layout comes from the file's name, as Looking Glass's own tools read it: `_qs8x6a0.75` is 8 columns, 6 rows, views of aspect 0.75. For a quilt whose name does not say, give it:

```bash
./stepit-holo show my-quilt.png --columns 8 --rows 6
```

If the depth looks inside out, near parts behind far ones, the quilt's views go the other way. Add `--reverse`.

The sample quilt, [`quilts/wasp_qs8x6a0.75.jpg`](quilts/wasp_qs8x6a0.75.jpg), is a quilt to compare yours with: it is known to look right on a Portrait.

### Check the Looking Glass with Numbered Views

```bash
./stepit-holo numbers
```

It shows a test quilt whose 48 views each show their number, 1 to 48, large, on a colour of their own. Through the lenses, one number fills the screen, and it changes in order as you move your head sideways. Some ghosting of the next numbers is normal: neighbouring views are this different only in the test. A mix of numbers across the screen, or a white blur, means that the calibration is wrong, or that the window does not cover the Looking Glass exactly. `--quilt-output numbers_qs8x6a0.75.png` saves the test quilt instead of showing it.

### Save a Hologram

```bash
./stepit-holo render quilts/wasp_qs8x6a0.75.jpg -o hologram.png
```

It saves the image the Looking Glass would show, of the screen's size, e.g. 1536 x 2048, without showing it: it needs no desktop. It still needs the calibration: the Looking Glass's drive, or `--calibration visual.json`, a copy of it.

### See the Calibration

```bash
./stepit-holo calibration
```

It prints where it found the calibration, and the values it derives from it. Every command takes `--calibration <file>` to use a copy of `visual.json` instead of the drive's, e.g. on a computer the Looking Glass is not plugged into.

## Use It as a Library

```python
import numpy as np
from PIL import Image

from stepit_holo import Interleaver, Layout, find_calibration

calibration = find_calibration()
quilt = np.asarray(Image.open("quilts/wasp_qs8x6a0.75.jpg").convert("RGB"))
interleaver = Interleaver(calibration, Layout(8, 6), quilt.shape[1], quilt.shape[0])
hologram = interleaver(quilt)  # An RGB array of the screen's size.
```

An `Interleaver` works out once which sub-pixel of the quilt each sub-pixel of the screen takes, about a third of a second on a PC, and keeps the table in `~/.cache/stepit-holo`. Every quilt of the same layout and size then takes a lookup, about 15 ms on a PC. `stepit_holo.viewer.show(hologram)` shows it, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Tests

```bash
python3 -m unittest discover tests
```

The tests need no display: they check the calibration, the layouts, the interleaving against views checked through a Portrait's lenses, the test quilt and the command line.

## Troubleshooting

**`no Looking Glass found`.** The display's drive is not mounted. Check that its USB cable is plugged into this computer and carries data: `lsusb` lists `Looking Glass Portrait`, or your model, once it does, and the desktop mounts the drive a few seconds later.

**`No monitor of 1536 x 2048`.** The Looking Glass is not part of the desktop at its own resolution: it is off, not on HDMI, mirrored instead of joined, or scaled by a fractional factor. In the display settings, join it to the desktop, at 100% or a whole factor such as 200%.

**A grid of small images through the lenses.** The quilt is shown flat, as by a program that does not interleave it, e.g. Looking Glass Bridge in its window. Close the other program, and show the quilt with `stepit-holo show`.

**A mix of numbers with `stepit-holo numbers`.** The window is not exactly on the Looking Glass, or the calibration is another display's. Check `stepit-holo calibration` against the drive of the display, and that the desktop's scaling is a whole factor, e.g. 100% or 200%.

**Another Looking Glass model.** StepIt Holo uses the values that the Portrait's calibration holds, as Looking Glass's WebXR library uses them. A model whose `visual.json` has `subpixelCells` may lay out its sub-pixels differently, which StepIt Holo ignores: check with `stepit-holo numbers`.

## Licences

StepIt Holo is released under the MIT licence, see [`LICENSE`](LICENSE).

The interleaving follows the formulas of Looking Glass's lenticular shader as their [WebXR library](https://github.com/Looking-Glass/looking-glass-webxr) publishes them, under the Apache 2.0 licence. StepIt Holo contains none of their code, and is not made or endorsed by Looking Glass Factory. Looking Glass is their trademark.

| Software | Licence | Role |
|---|---|---|
| [numpy](https://numpy.org/) | BSD 3-Clause | The interleaving. |
| [Pillow](https://python-pillow.org/) | HPND, BSD-like | Reads and writes the images. |
| [PyGObject](https://pygobject.gnome.org/) and [GTK](https://www.gtk.org/) | LGPL 2.1 | The full-screen window. |
