# Play the Library One Medium after the Other, with Transitions

Pull request [#19](https://github.com/kineticsystem/holo-pi/pull/19), branch `playlist`.

## Goal

We want the Looking Glass to play quilts and videos one after the other. We choose which ones, how many seconds a quilt stays, and how often a video loops. We want common transitions between them.

## Decisions

**The server plays, not the page.** The Looking Glass goes on with the browser closed, and after a restart of the Pi. Only the server's player knows when a video has played its last frame.

**A tab next to the library.** **Play** lists the library's media, with a box to tick each, its seconds or its times, **Play**, **Stop** and **Repeat**. The tabs are links, `#/` and `#/play`, so that the back button and a reload work.

**The library's order.** The playlist has no order of its own: we order the library by dragging, and there is one order to know.

**Nothing is ticked at first.** The box in the header ticks everything. A new upload does not join by itself.

**A medium left out keeps its settings.** As a grade switched off keeps its values: `enabled` is false, and the seconds or the times stay.

**Two resources.** `/api/playlist` is what to play, and setting it shows nothing. `PUT /api/display` with `{"playlist": true}` plays it, as it shows anything else.

**Showing anything else ends it.** A click on a row of the library, the test pattern, an upload that shows its first file, or black. There is no state "paused" to explain.

**A change counts from the next medium on.** The server asks the playlist for the next medium each time, so ticking, reordering or removing need no restart.

**Without Repeat, it ends black.** A video that went on looping would not look like an end.

**A medium waits for the Looking Glass.** Its time counts from when it is on the screen. A video holds its frame while the screen is off, where before it skipped one at each try.

**A damaged file is left out.** The others play on, and the log says why.

**Not the player of #8.** That one went from one video into the next in the same decoder, for two videos only. Here, quilts and videos mix, and each video has a player of its own.

**Transitions blend two holograms, sub-pixel by sub-pixel.** Each sub-pixel belongs to one view, so each view fades into the same view of the other, and both keep their depth.

**Cut, cross fade, fade through black and fade through white.** One for the whole playlist, and how long it takes.

**No wipe, iris or dissolve.** We had them, and took them out again: fades are enough. A playlist kept with one of them cuts.

**No slide.** A hologram moved sideways is under other lenses. It would have to be interleaved again at each step, too slow to be smooth on a Pi.

**Two holograms kept, not two quilts.** Each is interleaved once, and a step only blends. Videos go through them too: the last frame of one stays still, the next one plays from its first frame.

**The screen's thread draws them, not a request's.** The API answers meanwhile. Stop, a cut or another picture does not wait for the end.

**Only in the playlist, and a cut by default.** A click on a row of the library still shows it at once. A playlist kept before plays as it did.

## Left Out

A change without a wait. The last picture, or a video's last frame, stays still until the next one is ready, and the transition starts then. It takes as long as showing that medium by hand: on a Pi 5, about 0.8 seconds for a quilt and 0.2 for a video.

A playlist of one video starts it again with that same short pause. Showing the video from the library loops it without one.

Several playlists, an order of their own, a medium twice, and buttons for the next and the previous medium.

Setting the seconds of every quilt in one go.

A transition per medium, at the end of a playlist that does not repeat, and from black at the server's first picture.

Transitions without the GPU.

## Open Items

It is checked with a fake screen, and the repo's quilts and videos, on a PC, the transitions with a PC's GPU off screen. It is deployed on a Pi 5, where a playlist of quilts plays with fade through black. To check on the Portrait: how smooth the transitions are, above all into a video, and how they look through the lenses.

The README's picture of the web page is older than the tabs, and is to be taken again on a Pi.
