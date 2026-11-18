# Darker Quilts, without Spheres

Pull request [#11](https://github.com/kineticsystem/holo-pi/pull/11), branch `darker-quilts`.

## Goal

The quilts of [`quilts/`](../../quilts/README.md) looked washed out on the Looking Glass: overexposed, without contrast. Make them deeper, and drop the scene that breaks the window.

## Decisions

**A black sky.** The renders' darkest pixels were about 30% grey: a navy-to-lavender sky, which the floor faded into. That haze, not the highlights, made them look washed out; under 0.1% of the pixels were clipped. A colour grade cannot remove a gradient without crushing the dark sides of the spheres, so `make_assets.py` renders the sky black, and the dark tiles of the floor neutral grey instead of blue.

**A grade on every frame.** An S-curve and 25% more saturation, `GRADE`, FFmpeg's `curves` and `eq` filters. The video goes through it as it is encoded; the still quilt and the preview through the same filter, so they match the video's first frame exactly.

**Perfect mirrors.** The sun of `orrery` and the ball of `bounce` reflected 80% and 85%, the rest a grey paint, and looked grey. They reflect 100% now. Against a black sky, their upper half shows black, as a mirror in a dark room does.

**No `spheres`.** Its three small spheres orbit at 0.85, wider than the screen's half-width, 0.75, and come out of the screen as they pass its sides: the edge of the Looking Glass cuts something in front of it, and the window breaks. The other scenes stay inside it. Its quilt, video and preview went; `helix_qs8x6a0.75.jpg` is the sample quilt of the README, the API document, the architecture and the tests instead.

## Left Out

[`make_spheres.py`](../../quilts/make_spheres.py) stays, with its old sky: it is the one script that interleaves for a calibration. Its scene would need its orbits inside the window before its quilts come back.
