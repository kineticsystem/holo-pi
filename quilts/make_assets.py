"""Renders the test quilts and quilt videos of this folder: four animated 3D scenes, ray traced on an NVIDIA GPU.

    python3 quilts/make_assets.py                    # every scene
    python3 quilts/make_assets.py helix --seconds 2  # one scene, shorter, to try a change

It needs PyTorch with CUDA, Pillow, and FFmpeg with NVENC, hevc_nvenc. Each scene gives, in this folder:

- <scene>_qs8x6a0.75.mp4, the quilt video: 20 seconds at 24 frames per second, HEVC, 3360 x 3360, which loops
  without a jump;
- <scene>_qs8x6a0.75.jpg, its first frame, a single quilt;
- <scene>_preview.png, the middle view of its first frame, to see what it is without a Looking Glass.

A quilt is 8 x 6 views of 420 x 560, seen by 48 cameras on a line, 35 degrees from the first to the last, with
off-axis projections that share the screen's rectangle, as Looking Glass's tools render a Portrait's quilts: view
0 is the camera on the left, at the bottom left of the quilt. The screen is 1.5 x 2 in the scene, in the plane
z = 0: what is in front of it comes out of the Looking Glass, what is behind goes into it. The sky is black, and
every frame is graded, with more contrast and more colour, so that the scenes do not look washed out.
"""

import argparse
import math
import subprocess
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image

HERE = Path(__file__).parent
COLUMNS, ROWS, VIEW_W, VIEW_H = 8, 6, 420, 560
VIEWS = COLUMNS * ROWS
SAMPLES = 2  # Rays per pixel in each direction, averaged: smooth edges.
SCREEN_H = 2.0
SCREEN_W = SCREEN_H * VIEW_W / VIEW_H
DISTANCE = 5.0
VIEW_CONE = math.radians(35)
FLOOR_Y = -0.9
FPS = 24
PERIOD = 20.0  # Every motion repeats in 20 seconds: the videos loop.
DEPTH = 2  # Reflections of reflections, at most.
GRADE = "curves=all='0/0 0.25/0.19 0.5/0.46 0.75/0.79 1/1',eq=saturation=1.25"  # An S-curve and more colour, FFmpeg's.
device = torch.device("cuda")
LIGHT = torch.tensor([-0.45, 1.0, 0.6], device=device)
LIGHT = LIGHT / LIGHT.norm()


# The scenes: each returns the spheres at time t, (centres S x 3, radii S, colours S x 3, reflectivity S), and the
# floor's reflectivity.

def hsv(h, s=0.75, v=1.0):
    """A colour of hue h, 0 to 1, as RGB."""
    k = (np.array([5, 3, 1]) + h * 6) % 6
    return v - v * s * np.clip(np.minimum(k, 4 - k), 0, 1)


def helix(t):
    """A double helix, turning, with a wave running up its strands, and rungs between them."""
    spheres = []
    levels = 18
    for k in range(levels):
        y = -0.72 + 1.55 * k / (levels - 1)
        a = 2 * math.pi * (1.4 * k / levels + 2 * t / PERIOD)
        swell = 1 + 0.35 * math.sin(2 * math.pi * (k / levels - 3 * t / PERIOD))
        for strand, hue in ((0, 0.02 + 0.12 * k / levels), (1, 0.5 + 0.15 * k / levels)):
            b = a + strand * math.pi
            spheres.append(((0.46 * math.cos(b), y, 0.46 * math.sin(b)), 0.085 * swell, hsv(hue), 0.05))
        if k % 2 == 0:
            for f in (0.3, 0.5, 0.7):
                x, z = 0.46 * math.cos(a) * (1 - 2 * f), 0.46 * math.sin(a) * (1 - 2 * f)
                spheres.append(((x, y, z), 0.035, hsv(0.15, 0.1), 0.2))
    return spheres, 0.25


def orrery(t):
    """A chrome sun, four planets on tilted orbits at their own speeds, and moons around two of them."""
    sun_y = 0.05 + 0.05 * math.sin(2 * math.pi * 2 * t / PERIOD)
    spheres = [((0.0, sun_y, 0.0), 0.27, (0.85, 0.85, 0.9), 1.0)]
    planets = [(0.42, 0.3, 3, 0.07, 0.6), (0.55, -0.25, -2, 0.09, 0.08), (0.66, 0.15, 1, 0.11, 0.33),
               (0.5, 0.55, 4, 0.06, 0.85)]
    for index, (radius, tilt, turns, size, hue) in enumerate(planets):
        a = 2 * math.pi * (turns * t / PERIOD + index / 4)
        x, y, z = radius * math.cos(a), 0.0, radius * math.sin(a)
        y, z = y * math.cos(tilt) - z * math.sin(tilt), y * math.sin(tilt) + z * math.cos(tilt)
        centre = (x, sun_y + y, z)
        spheres.append((centre, size, hsv(hue), 0.1))
        if index in (1, 2):
            m = 2 * math.pi * (6 * t / PERIOD + index * 0.3)
            spheres.append(((centre[0] + 0.17 * math.cos(m), centre[1] + 0.06 * math.sin(m),
                             centre[2] + 0.17 * math.sin(m)), 0.035, hsv(0.12, 0.2), 0.0))
    return spheres, 0.2


def bounce(t):
    """Nine balls bouncing on a reflecting floor at their own rhythms, a mirror ball in the middle, all turning."""
    spheres = []
    turn = 2 * math.pi * t / PERIOD
    beats = [4, 5, 6, 8, 0, 10, 5, 4, 6]
    for index, beat in enumerate(beats):
        gx, gz = index % 3 - 1, index // 3 - 1
        x, z = 0.42 * gx, 0.42 * gz
        x, z = x * math.cos(turn) - z * math.sin(turn), x * math.sin(turn) + z * math.cos(turn)
        if beat == 0:  # The mirror ball, hovering.
            y = FLOOR_Y + 0.45 + 0.05 * math.sin(2 * math.pi * 3 * t / PERIOD)
            spheres.append(((x, y, z), 0.19, (0.9, 0.9, 0.95), 1.0))
            continue
        phase = (beat * t / PERIOD + index * 0.137) % 1
        y = FLOOR_Y + 0.11 + 1.1 * 4 * phase * (1 - phase) * (0.55 + 0.05 * index)  # A parabola per bounce.
        spheres.append(((x, y, z), 0.11, hsv(index / 9), 0.08))
    return spheres, 0.35


def knot(t):
    """A chain of beads running along a trefoil knot, which turns and tilts."""
    spheres = []
    beads = 72
    turn, tilt = 2 * math.pi * t / PERIOD, 0.35 + 0.15 * math.sin(2 * math.pi * t / PERIOD)
    for k in range(beads):
        phi = 2 * math.pi * (k / beads + t / PERIOD)
        r = math.cos(2 * phi) + 2.2
        x, y, z = 0.17 * r * math.cos(3 * phi), 0.17 * r * math.sin(3 * phi), -0.3 * math.sin(2 * phi)
        y, z = y * math.cos(tilt) - z * math.sin(tilt), y * math.sin(tilt) + z * math.cos(tilt)
        x, z = x * math.cos(turn) - z * math.sin(turn), x * math.sin(turn) + z * math.cos(turn)
        spheres.append(((x, y + 0.08, z), 0.06, hsv(k / beads, 0.7), 0.15))
    return spheres, 0.2


SCENES = {"helix": helix, "orrery": orrery, "bounce": bounce, "knot": knot}


# The ray tracer.

def hit_spheres(origin, direction, scene, group=8):
    """The nearest sphere each ray hits: its distance, inf for none, and its index. The directions are unit length.
    The rays meet `group` spheres at a time: one at a time is several times slower on a GPU."""
    centres, radii = scene["centres"], scene["radii"]
    best = torch.full(direction.shape[:1], math.inf, device=device)
    which = torch.full(direction.shape[:1], -1, dtype=torch.long, device=device)
    for first in range(0, centres.shape[0], group):
        oc = origin[:, None, :] - centres[None, first:first + group]
        b = (oc * direction[:, None, :]).sum(-1)
        disc = b * b - ((oc * oc).sum(-1) - radii[None, first:first + group] ** 2)
        root = disc.clamp(min=0).sqrt()
        near = -b - root
        d = torch.where(near > 1e-4, near, -b + root)
        d = torch.where((disc > 0) & (d > 1e-4), d, torch.full_like(d, math.inf))
        nearest, index = d.min(dim=1)
        closer = nearest < best
        best = torch.where(closer, nearest, best)
        which = torch.where(closer, index + first, which)
    return best, which


def background(direction):
    """The sky, black: the scene floats in the dark, and a mirror shows only what is around it."""
    return torch.zeros_like(direction)


def shade(origin, direction, scene, depth=0):
    """The colour each ray sees, linear RGB."""
    colour = background(direction)
    sphere_d, which = hit_spheres(origin, direction, scene)
    floor_d = torch.where(direction[:, 1] < -1e-6, (FLOOR_Y - origin[:, 1]) / direction[:, 1].clamp(max=-1e-6),
                          torch.full_like(sphere_d, math.inf))
    floor_d = torch.where(floor_d > 1e-4, floor_d, torch.full_like(floor_d, math.inf))
    on_floor = torch.isfinite(floor_d) & (floor_d < sphere_d)
    on_sphere = (which >= 0) & ~on_floor

    if on_floor.any():
        o, d = origin[on_floor], direction[on_floor]
        p = o + d * floor_d[on_floor, None]
        checker = ((torch.floor(p[:, 0] * 2.5) + torch.floor(p[:, 2] * 2.5)) % 2)[:, None]
        base = torch.where(checker > 0, torch.tensor([0.8, 0.8, 0.78], device=device),
                           torch.tensor([0.12, 0.12, 0.12], device=device))
        shadow, _ = hit_spheres(p + torch.tensor([0, 1e-3, 0], device=device), LIGHT.expand_as(p), scene)
        lit = torch.where(torch.isfinite(shadow), 0.3, 1.0)[:, None]
        surface = base * (0.25 + 0.75 * LIGHT[1] * lit)
        if depth < DEPTH and scene["floor_reflect"] > 0:
            mirrored = d * torch.tensor([1.0, -1.0, 1.0], device=device)
            reflection = shade(p + torch.tensor([0, 1e-3, 0], device=device), mirrored, scene, depth + 1)
            surface = surface * (1 - scene["floor_reflect"]) + reflection * scene["floor_reflect"]
        fade = (torch.exp(-(-p[:, 2] - 0.4).clamp(min=0) * 0.45) * torch.exp(-(p[:, 2] - 1.6).clamp(min=0)))[:, None]
        colour[on_floor] = surface * fade + colour[on_floor] * (1 - fade)

    if on_sphere.any():
        o, d, index = origin[on_sphere], direction[on_sphere], which[on_sphere]
        p = o + d * sphere_d[on_sphere, None]
        normal = p - scene["centres"][index]
        normal = normal / normal.norm(dim=-1, keepdim=True)  # Unit length, or a reflection drifts off its sphere.
        albedo, reflect = scene["colours"][index], scene["reflect"][index, None]
        diffuse = (normal @ LIGHT).clamp(min=0)
        shadow, _ = hit_spheres(p + normal * 1e-3, LIGHT.expand_as(p), scene)
        diffuse = torch.where(torch.isfinite(shadow), diffuse * 0.25, diffuse)[:, None]
        mirrored = d - 2 * (d * normal).sum(-1, keepdim=True) * normal
        mirrored = mirrored / mirrored.norm(dim=-1, keepdim=True)
        specular = ((mirrored @ LIGHT).clamp(min=0) ** 50)[:, None]
        rim = ((1 - (-(d * normal).sum(-1)).clamp(min=0)) ** 3)[:, None]
        surface = albedo * (0.12 + 0.88 * diffuse) + rim * 0.12
        if depth < DEPTH and bool((reflect > 0).any()):
            reflection = shade(p + normal * 1e-3, mirrored, scene, depth + 1)
            surface = surface * (1 - reflect) + reflection * reflect
        colour[on_sphere] = surface + specular * 0.9
    return colour


def rays():
    """Every camera's rays through every pixel, SAMPLES x SAMPLES per pixel: origins V x 3, directions V x N x 3."""
    half = DISTANCE * math.tan(VIEW_CONE / 2)
    cameras = torch.zeros(VIEWS, 3, device=device)
    cameras[:, 0] = torch.linspace(-half, half, VIEWS, device=device)
    cameras[:, 2] = DISTANCE
    w, h = VIEW_W * SAMPLES, VIEW_H * SAMPLES
    x = (torch.arange(w, device=device) + 0.5) / w * SCREEN_W - SCREEN_W / 2
    y = SCREEN_H / 2 - (torch.arange(h, device=device) + 0.5) / h * SCREEN_H
    y, x = torch.meshgrid(y, x, indexing="ij")
    targets = torch.stack([x, y, torch.zeros_like(x)], -1).reshape(1, -1, 3)
    directions = targets - cameras[:, None, :]
    return cameras, directions / directions.norm(dim=-1, keepdim=True)


def render_quilt(make_scene, t, cameras, directions):
    spheres, floor_reflect = make_scene(t)
    scene = {"centres": torch.tensor([s[0] for s in spheres], device=device, dtype=torch.float32),
             "radii": torch.tensor([s[1] for s in spheres], device=device, dtype=torch.float32),
             "colours": torch.tensor(np.array([s[2] for s in spheres]), device=device, dtype=torch.float32),
             "reflect": torch.tensor([s[3] for s in spheres], device=device, dtype=torch.float32),
             "floor_reflect": floor_reflect}
    quilt = torch.empty(ROWS * VIEW_H, COLUMNS * VIEW_W, 3, dtype=torch.uint8, device=device)
    for first in range(0, VIEWS, COLUMNS):  # One row of views at a time.
        views = range(first, first + COLUMNS)
        origin = cameras[first:first + COLUMNS, None, :].expand(-1, directions.shape[1], -1).reshape(-1, 3)
        colour = shade(origin, directions[first:first + COLUMNS].reshape(-1, 3), scene)
        colour = colour.reshape(COLUMNS, VIEW_H, SAMPLES, VIEW_W, SAMPLES, 3).mean(dim=(2, 4))
        pixels = (colour.clamp(0, 1) ** (1 / 2.2) * 255 + 0.5).to(torch.uint8)
        for offset, view in enumerate(views):
            row, column = ROWS - 1 - view // COLUMNS, view % COLUMNS
            quilt[row * VIEW_H:(row + 1) * VIEW_H, column * VIEW_W:(column + 1) * VIEW_W] = pixels[offset]
    return quilt.cpu().numpy()


def graded(image):
    """An RGB image through GRADE, as the video's frames go."""
    h, w = image.shape[:2]
    out = subprocess.run(["ffmpeg", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-i", "-",
                          "-vf", GRADE, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         input=np.ascontiguousarray(image).tobytes(), capture_output=True, check=True).stdout
    return np.frombuffer(out, np.uint8).reshape(h, w, 3)


def make(name, seconds):
    cameras, directions = rays()
    stem = HERE / f"{name}_qs8x6a0.75"
    frames = round(seconds * FPS)
    size = f"{COLUMNS * VIEW_W}x{ROWS * VIEW_H}"
    ffmpeg = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", size, "-r", str(FPS),
         "-i", "-", "-vf", GRADE, "-c:v", "hevc_nvenc", "-preset", "p7", "-tune", "hq", "-rc", "vbr", "-cq", "20",
         "-b:v", "0", "-pix_fmt", "yuv420p", "-tag:v", "hvc1", "-movflags", "+faststart", f"{stem}.mp4"],
        stdin=subprocess.PIPE)
    start = time.perf_counter()
    for n in range(frames):
        quilt = render_quilt(SCENES[name], n / FPS, cameras, directions)
        if n == 0:
            Image.fromarray(graded(quilt)).save(f"{stem}.jpg", quality=92)
            middle = VIEWS // 2
            row, column = ROWS - 1 - middle // COLUMNS, middle % COLUMNS
            view = quilt[row * VIEW_H:(row + 1) * VIEW_H, column * VIEW_W:(column + 1) * VIEW_W]
            Image.fromarray(graded(view)).save(HERE / f"{name}_preview.png")
        ffmpeg.stdin.write(quilt.tobytes())
        if n % FPS == 0:
            print(f"{name}: frame {n}/{frames}, {time.perf_counter() - start:.0f} s", flush=True)
    ffmpeg.stdin.close()
    ffmpeg.wait()
    print(f"{name}: {frames} frames in {time.perf_counter() - start:.0f} s, "
          f"{(HERE / f'{stem}.mp4').stat().st_size / 1e6:.1f} MB", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("scenes", nargs="*", help=f"some of {', '.join(SCENES)}; default: all of them")
    parser.add_argument("--seconds", type=float, default=PERIOD)
    arguments = parser.parse_args()
    unknown = set(arguments.scenes) - set(SCENES)
    if unknown:
        parser.error(f"no scene {', '.join(sorted(unknown))}: one of {', '.join(SCENES)}")
    arguments.scenes = arguments.scenes or list(SCENES)
    with torch.no_grad():
        for name in arguments.scenes:
            make(name, arguments.seconds)


if __name__ == "__main__":
    main()
