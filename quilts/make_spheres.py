"""Renders an animated 3D scene as quilts, interleaves them for one Looking Glass, and encodes a hologram video.

    python3 quilts/make_spheres.py calibration.json out.mp4 [--seconds 5] [--fps 24] [--encoder libx265|hevc_nvenc]
    python3 quilts/make_spheres.py calibration.json spheres_qs8x6a0.75.mp4 --quilts --encoder hevc_nvenc

The scene is ray traced with numpy: three spheres orbit a fourth above a checkered floor, in front of and behind
the screen's plane, so that the depth shows. Each frame is a quilt of 8 x 6 views of 420 x 560, seen by 48 cameras
on a line, with off-axis projections that share the screen's rectangle, as Looking Glass's tools render: view 0 is
the camera on the left. Each quilt is interleaved with holo_pi's Interleaver, then doubled in width, each pixel
twice side by side, as the Portrait's own videos, and piped to FFmpeg.
"""

import argparse
import json
import math
import os
import subprocess
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # The checkout, for holo_pi.
from holo_pi import Calibration, Interleaver, Layout  # noqa: E402

COLUMNS, ROWS, VIEW_W, VIEW_H = 8, 6, 420, 560
VIEWS = COLUMNS * ROWS
SCREEN_H = 2.0  # The screen's rectangle in the scene, centred on the origin, in the plane z = 0.
SCREEN_W = SCREEN_H * VIEW_W / VIEW_H
DISTANCE = 5.0  # From the cameras to the screen's plane.
VIEW_CONE = math.radians(35)  # From the left camera to the right one, as a Portrait's.
LIGHT = np.array([-0.5, 1.0, 0.7]) / np.linalg.norm([-0.5, 1.0, 0.7])
FLOOR_Y = -0.9


def spheres(t):
    """(centre, radius, colour) of each sphere at time t, in seconds: one in the middle, three orbiting it."""
    result = [((0.0, -0.25 + 0.08 * math.sin(2 * math.pi * t / 2.5), 0.0), 0.38, (1.0, 0.55, 0.15))]
    colours = [(0.2, 0.6, 1.0), (0.95, 0.25, 0.35), (0.3, 0.9, 0.45)]
    for k, colour in enumerate(colours):
        a = 2 * math.pi * (t / 5 + k / 3)  # One turn in 5 seconds: the video loops.
        result.append(((0.85 * math.cos(a), 0.15 + 0.25 * math.sin(2 * a), 0.85 * math.sin(a)), 0.2, colour))
    return result


def hit_spheres(origin, direction, balls):
    """The nearest hit of each ray: distance (inf if none) and the index of the sphere."""
    best = np.full(direction.shape[0], np.inf)
    which = np.full(direction.shape[0], -1)
    for index, (centre, radius, _) in enumerate(balls):
        oc = origin - np.asarray(centre)
        b = (direction * oc).sum(-1)
        c = (oc * oc).sum(-1) - radius * radius
        disc = b * b - c
        root = np.sqrt(np.maximum(disc, 0))
        d = -b - root
        d = np.where(d > 1e-4, d, -b + root)
        ok = (disc > 0) & (d > 1e-4) & (d < best)
        best = np.where(ok, d, best)
        which = np.where(ok, index, which)
    return best, which


def render_view(view, t):
    """One view, an RGB array of VIEW_H x VIEW_W, from camera `view` at time t."""
    balls = spheres(t)
    half = DISTANCE * math.tan(VIEW_CONE / 2)
    camera = np.array([-half + 2 * half * view / (VIEWS - 1), 0.0, DISTANCE])
    x = (np.arange(VIEW_W) + 0.5) / VIEW_W * SCREEN_W - SCREEN_W / 2
    y = SCREEN_H / 2 - (np.arange(VIEW_H) + 0.5) / VIEW_H * SCREEN_H
    x, y = np.meshgrid(x, y)
    target = np.stack([x, y, np.zeros_like(x)], -1).reshape(-1, 3)
    direction = target - camera
    direction /= np.linalg.norm(direction, axis=-1, keepdims=True)
    origin = np.broadcast_to(camera, direction.shape)

    colour = np.zeros_like(direction)
    # The background: a dark gradient.
    colour[:] = (0.04, 0.05, 0.09)
    colour += (0.06 * (direction[:, 1:2] + 0.3)).clip(0) * np.array([0.6, 0.7, 1.0])

    # The floor, a checkerboard that fades into the distance.
    floor_d = np.where(direction[:, 1] < -1e-6, (FLOOR_Y - origin[:, 1]) / np.minimum(direction[:, 1], -1e-6), np.inf)
    sphere_d, which = hit_spheres(origin, direction, balls)
    on_floor = np.isfinite(floor_d) & (floor_d < sphere_d)
    if on_floor.any():
        p = origin[on_floor] + direction[on_floor] * floor_d[on_floor, None]
        checker = ((np.floor(p[:, 0] * 2.5) + np.floor(p[:, 2] * 2.5)) % 2).astype(float)
        base = np.where(checker[:, None] > 0, [0.85, 0.85, 0.82], [0.18, 0.2, 0.26])
        # Shadows of the spheres, towards the light.
        shadow_d, _ = hit_spheres(p, np.broadcast_to(LIGHT, p.shape), balls)
        lit = np.where(np.isfinite(shadow_d), 0.35, 1.0)
        fade = np.exp(-np.maximum(-p[:, 2] - 0.5, 0) * 0.35) * np.exp(-np.maximum(p[:, 2] - 1.5, 0) * 0.6)
        colour[on_floor] = base * (lit * fade)[:, None] + colour[on_floor] * (1 - fade[:, None])

    on_ball = which >= 0
    if on_ball.any():
        p = origin[on_ball] + direction[on_ball] * sphere_d[on_ball, None]
        centres = np.array([b[0] for b in balls])[which[on_ball]]
        radii = np.array([b[1] for b in balls])[which[on_ball]]
        normal = (p - centres) / radii[:, None]
        albedo = np.array([b[2] for b in balls])[which[on_ball]]
        diffuse = (normal @ LIGHT).clip(0)
        shadow_d, _ = hit_spheres(p + normal * 1e-3, np.broadcast_to(LIGHT, p.shape), balls)
        diffuse = np.where(np.isfinite(shadow_d), diffuse * 0.3, diffuse)
        reflected = direction[on_ball] - 2 * (direction[on_ball] * normal).sum(-1, keepdims=True) * normal
        specular = (reflected @ LIGHT).clip(0) ** 40
        rim = (1 - (-(direction[on_ball] * normal).sum(-1)).clip(0)) ** 3
        colour[on_ball] = albedo * (0.15 + 0.85 * diffuse[:, None]) + specular[:, None] * 0.9 + rim[:, None] * 0.15

    return (colour.clip(0, 1) ** (1 / 2.2) * 255 + 0.5).astype(np.uint8).reshape(VIEW_H, VIEW_W, 3)


def render_quilt(t):
    """The quilt at time t: view 0 at the bottom left, rows from the bottom up."""
    quilt = np.empty((ROWS * VIEW_H, COLUMNS * VIEW_W, 3), np.uint8)
    for view in range(VIEWS):
        row, column = ROWS - 1 - view // COLUMNS, view % COLUMNS
        quilt[row * VIEW_H:(row + 1) * VIEW_H, column * VIEW_W:(column + 1) * VIEW_W] = render_view(view, t)
    return quilt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("calibration", help="the calibration, as GET /calibration answers it")
    parser.add_argument("output")
    parser.add_argument("--seconds", type=float, default=5)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--encoder", default="libx265")
    parser.add_argument("--quilt-png", help="save the first quilt, to look at")
    parser.add_argument("--quilts", action="store_true", help="encode the quilts themselves, not interleaved")
    arguments = parser.parse_args()

    calibration = Calibration(**json.load(open(arguments.calibration)))
    frames = round(arguments.seconds * arguments.fps)
    times = [n / arguments.fps for n in range(frames)]
    interleaver = Interleaver(calibration, Layout(COLUMNS, ROWS), COLUMNS * VIEW_W, ROWS * VIEW_H)
    width, height = 2 * calibration.width, calibration.height
    if arguments.quilts:
        width, height = COLUMNS * VIEW_W, ROWS * VIEW_H

    if arguments.encoder == "hevc_nvenc":
        quality = ["-preset", "p7", "-tune", "hq", "-rc", "vbr", "-cq", "19", "-b:v", "0"]
    else:
        quality = ["-preset", "medium", "-crf", "18", "-x265-params", "log-level=error"]
    ffmpeg = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}",
         "-r", str(arguments.fps), "-i", "-", "-c:v", arguments.encoder, *quality, "-pix_fmt", "yuv420p",
         "-tag:v", "hvc1", "-movflags", "+faststart", arguments.output], stdin=subprocess.PIPE)

    clock = {"render": 0.0, "interleave": 0.0, "encode": 0.0}
    start = time.perf_counter()
    with Pool(len(os.sched_getaffinity(0))) as pool:
        mark = time.perf_counter()
        for n, quilt in enumerate(pool.imap(render_quilt, times)):
            now = time.perf_counter()
            clock["render"] += now - mark  # Waiting for the renderers, which run ahead in parallel.
            if n == 0 and arguments.quilt_png:
                from PIL import Image
                Image.fromarray(quilt).save(arguments.quilt_png)
            hologram = quilt if arguments.quilts else np.repeat(interleaver(quilt), 2, axis=1)  # Each pixel twice.
            mark = time.perf_counter()
            clock["interleave"] += mark - now
            ffmpeg.stdin.write(hologram.tobytes())
            now = time.perf_counter()
            clock["encode"] += now - mark
            mark = now
            print(f"\rframe {n + 1}/{frames}", end="", flush=True)
    ffmpeg.stdin.close()
    wait = time.perf_counter()
    ffmpeg.wait()
    clock["encode"] += time.perf_counter() - wait
    total = time.perf_counter() - start
    print(f"\n{frames} frames, {arguments.seconds} s at {arguments.fps} fps, with {arguments.encoder}: "
          f"{total:.1f} s in all, {os.path.getsize(arguments.output) / 1e6:.1f} MB; "
          + ", ".join(f"{k} {v:.1f} s" for k, v in clock.items()))


if __name__ == "__main__":
    main()
