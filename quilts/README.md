# Quilts

Quilts and quilt videos to try HoloPi with, and the scripts that render them. Every one is a Portrait's quilt: 8 x 6 views of 420 x 560, 3360 x 3360, view 0 at the bottom left.

## The Scenes

| Scene | What it shows | Video |
|---|---|---|
| `helix` | A double helix turning, with a wave running up its strands and rungs between them. | 20 seconds, 117 MB |
| `orrery` | A mirror sun, four planets on tilted orbits, and moons around two of them. | 20 seconds, 79 MB |
| `bounce` | Nine balls bouncing at their own rhythms on a reflecting floor, around a mirror ball. | 20 seconds, 113 MB |
| `knot` | A chain of beads running along a trefoil knot, which turns and tilts. | 20 seconds, 118 MB |

Each scene has three files:

- `<scene>_qs8x6a0.75.mp4`, the quilt video: HEVC at 24 frames per second, which loops without a jump, and which a Raspberry Pi 5 decodes with its hardware decoder;
- `<scene>_qs8x6a0.75.jpg`, its first frame, a single quilt;
- `<scene>_preview.png`, the middle view of that frame, to see what it is without a Looking Glass.

`helix_qs8x6a0.75.jpg` is the sample quilt of the [README](../README.md).

Upload one and show it, from the checkout, or drop them on the Pi's web page, http://holo.local:8095:

```bash
curl -F file=@quilts/helix_qs8x6a0.75.jpg -F play=true http://holo.local:8095/api/media
curl -F file=@quilts/helix_qs8x6a0.75.mp4 -F play=true http://holo.local:8095/api/media
```

## Render Them

[`make_assets.py`](make_assets.py) ray traces `helix`, `orrery`, `bounce` and `knot` on an NVIDIA GPU, with reflections and shadows, and writes their three files here. The sky is black, the sun of `orrery` and the ball of `bounce` are perfect mirrors, and every frame goes through a grade, `GRADE`, an S-curve and 25% more saturation: without them the scenes looked washed out on the Looking Glass, with a lavender haze where black should be. It needs PyTorch with CUDA, Pillow, and FFmpeg with NVENC, `hevc_nvenc`. A scene takes from 3 to 23 minutes on an RTX 4090:

```bash
python3 quilts/make_assets.py
python3 quilts/make_assets.py helix --seconds 2
```

The second renders one scene, shorter, to try a change.

[`make_spheres.py`](make_spheres.py) renders `spheres`, three spheres orbiting an orange one, with numpy on the processor, in about 6 minutes. Its quilts are not kept here: the orbiting spheres come out of the screen and cross its sides, so the edge of the Looking Glass cuts them, and they break the window. It needs a calibration, as `GET /api/calibration` answers it, and interleaves for it unless `--quilts` says to keep the quilts:

```bash
curl -o calibration.json http://holo.local:8095/api/calibration
python3 quilts/make_spheres.py calibration.json spheres_qs8x6a0.75.mp4 --quilts --encoder hevc_nvenc --seconds 5
```
