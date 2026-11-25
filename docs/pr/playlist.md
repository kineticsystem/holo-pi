# Play the Library One Medium after the Other

Branch `playlist`.

## Goal

We want the Looking Glass to play quilts and videos one after the other. We choose which ones, how many seconds a quilt stays, and how often a video loops.

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

## Left Out

A gapless change. The last picture stays until the next one is ready. It takes as long as showing that medium by hand: on a Pi 5, about 0.8 seconds for a quilt and 0.2 for a video.

A playlist of one video starts it again with that same short pause. Showing the video from the library loops it without one.

Several playlists, an order of their own, a medium twice, and buttons for the next and the previous medium.

Setting the seconds of every quilt in one go.

## Open Items

It is checked with a fake screen, and the repo's quilts and videos, on a PC: not yet on a Pi with a Portrait.

The README's picture of the web page is older than the tabs, and is to be taken again on a Pi.
