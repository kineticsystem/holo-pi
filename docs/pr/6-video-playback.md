# Videos on the GPU, a Library, a REST API and a Web Page

Pull request [#6](https://github.com/kineticsystem/holo-pi/pull/6), branch `video-playback`.

## Goal

Play videos on the Looking Glass, in a loop. Upload a quilt or a video of quilts, and see it at once, with nothing to know about the Looking Glass: the Pi has its calibration.

Keep the media on the Pi, and show them later by id or name, without uploading them again.

Try it all from a web page, without knowing the API; the API documented with Swagger.

The first use is animations made elsewhere, e.g. a desk buddy's.

## What We Found

The Portrait keeps its videos on its own drive, next to `LKG_calibration`: 67 files, `*__lkgrec.mp4`, 407 MB. One of them, `Anna.jpg__lkgrec.mp4`, is HEVC, 3072 x 2048, 12 frames per second, 118 frames.

They are not quilts. Each frame is already a hologram: its stripes repeat every 6.0 to 6.4 pixels, against 6.22 from the calibration's pitch, and slant 0.141 pixels per row, against 0.140 from its tilt.

Each pair of pixels side by side is nearly the same: a mean difference of 1.5, against 22 between pairs. So the picture is 1536 x 2048, the screen's, stored twice as wide. Our guess: the encoding's 4:2:0 keeps one colour for two pixels side by side, and doubling the width keeps a colour per pixel of the screen.

## How It Went

First, hologram videos only, as the Portrait's own: the Pi decodes and shows the frames as they are.

Then quilt videos. Converting one on the Pi into a hologram video worked, but took about 24 seconds for 5 seconds of video. Interleaving each frame on the GPU as it is shown starts at once, and plays on any Looking Glass. We tried it in a spike, then built it in.

Then the Pi 5's hardware decoder, when a detailed video played in slow motion: the processor could not decode it fast enough.

Then the uploads. A 120 MB video took about 2.8 seconds from upload to screen: 1.4 for the network, close to gigabit's limit, 0.7 for a second copy on the Pi, 0.6 to start. Keeping the media on the Pi makes showing one 0.1 to 0.8 seconds, with nothing sent.

Then the API went REST, on `/api`, and a web page came, as the StepIt projects have them.

## Decisions

**Quilt videos interleaved by the GPU as they play.** The Pi 5's GPU interleaves a Portrait's screen in about 27 ms; its processor's table lookup takes about 80. Converting once would tie the file to one Looking Glass.

**Hologram videos too.** The Portrait's own play as they are. A video without a layout in its name or fields is one.

**A YUV frame to the GPU, not RGB.** The spike measured the copy to the GPU: RGB 53 ms, which Mesa repacks on the processor; RGBA 27 ms, with FFmpeg's conversion; YUV planes 6 ms. The shader turns YUV into RGB.

**Two sets of textures, used in turn.** With one set, copying the next frame waited for the GPU to finish drawing from it: 23.5 frames per second. With two, 26.

**Page flips that do not wait.** `drmModeSetCrtc()` for every frame does not wait for the screen's refresh. Both screens flip at the refresh, and the next picture waits for the flip, not the one being shown.

**The copy as 32-bit pixels.** Copying one column of each two byte by byte took 27 ms on the Pi; as 32-bit numbers, 3 ms. That alone took a hologram video at 30 frames per second from 18 to 28.

**A decoder thread, 16 frames ahead.** Opening the file again at each round stalled the screen up to 0.4 seconds, while FFmpeg's threads filled up. With the frames decoded ahead, a loop has no pause.

**The hardware decoder, with Raspberry Pi's FFmpeg.** Debian's FFmpeg does not reach the Pi 5's HEVC decoder; Raspberry Pi's does, with the same library versions, so Debian's `python3-av` uses it as it is. The helix, 3360 x 3360 at 49 Mbit/s, went from 10 frames per second with four cores to 23.4 with less than one.

**Raspberry Pi OS's copy of their key, in the repo.** The key on their web site has SHA-1 signatures, which Debian 13's apt has refused since February 2026.

**`frame_rate` and `decoder` in the status.** Slow motion is easy to see and hard to explain: these two say why.

**`501` without PyAV.** The quilts keep working without it. A `503` would have said the video is kept, which it is not.

**A warning for a video not in H.265.** The Pi 5 decodes only HEVC in hardware. The upload's answer, the media and the display carry the warning, with the command to encode it again; the page shows one per file, and counts them.

**A library, with names unique.** Every upload is kept, `library/` and `index.json` in the state folder. A name addresses a medium as its id does, so a client needs no ids; an upload of the same name replaces it and keeps its id. What was shown last is `shown.json`, an id. The one quilt or video an older version kept moves into the library at the first start.

**REST, on `/api`.** `/api/media` and `/api/display`, with GET, POST, PUT and DELETE; `201` with `Location`, `204`, and `{"error": ...}` for every error, as StepIt Editor's. The old routes, `/quilt`, `/video`, `/numbers`, went: the page and Swagger replace them for trying, and nothing else used them yet.

**Swagger UI from the Pi.** FastAPI loads Swagger UI from a CDN by default; the Pi may have no internet. Its files come from `swagger-ui-dist`, copied by the page's build, served on `/api/docs/assets`. `@scarf/scarf`, its usage tracking, is refused in `pnpm-workspace.yaml`.

**The web page in the image.** React, Vite, TypeScript and pnpm, with the versions of stepit-macro's page, and no other library: `useReducer` behind a Context for the store. A first stage of the Dockerfile builds it, so the Pi needs no Node; the build's context became the repo, and `.dockerignore` keeps `quilts/` out.

**Uploads one after another.** Dropped files go into a queue, sent one at a time, each stoppable; one that fails does not stop the next. With "show it at once", the first is shown.

**CI on GitHub.** The Python tests in `debian:trixie`, with Debian's packages; Mesa's llvmpipe runs the GPU's tests on a runner without a GPU. The page's type check, tests and build. The image's build, for amd64.

## Measured on the Pi 5

| Video | Decoder | Frames per second | CPU, of 400% |
|---|---|---|---|
| `Anna.jpg__lkgrec.mp4`, hologram, 12 fps | processor | 12.1 | 46% |
| The same, re-encoded at 30 fps | processor | 30.0 | 286% |
| Spheres, quilt, 3360 x 3360, 21 Mbit/s, 24 fps | processor | 23.6 to 24.0 | 316% |
| Helix, quilt, 3360 x 3360, 49 Mbit/s, 24 fps | processor | about 10 | 392% |
| The same | hardware | 23.2 to 23.4 | 87% |

The last frame a second or so is the GPU's: its 27 ms a frame leave little room at 24 frames per second.

## Left Out

A command line `holo-pi play`. The server and its page are the use.

A WebSocket for the page. It asks what is shown every 2 seconds.

Thumbnails in the library. A quilt is 3360 x 3360; the page would need the server to make small ones.

Writing an upload straight to its place, without the second copy: about 0.7 seconds of 2.8 for a 120 MB video.

The hardware decoder's frames straight to the GPU, as DRM PRIME buffers imported by EGL. PyAV does not give their descriptors, and the copy costs less than a core.

A faster shader, for 30 frames per second. See [How to Extend HoloPi](../ARCHITECTURE.md#how-to-extend-holopi).

## Test Material

[`quilts/`](../../quilts/README.md) has quilt videos and quilts rendered for these tests, and the scripts that render them. The wasp's quilt went; `spheres_qs8x6a0.75.jpg`, ours, is the sample now. The videos, about 430 MB, are not committed yet.

## Open Items

Where the test videos live: in the repo with Git LFS, or as release assets.
