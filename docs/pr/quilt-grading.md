# Grade a Quilt on the Looking Glass

Branch `quilt-grading`. Experimental.

## Goal

We want to grade a quilt on the Looking Glass itself: move a slider on the web page, see the hologram change. It must feel immediate, run on the Pi, and leave the page as it is, but for one button.

## Decisions

**The tools are StepIt Grader's.** Same names, same ranges, same math: color, light, tone curve, colour mixer, effects. We compared the two on one view of a photograph and of a quilt. Most tools differ by less than half a level of 255 on average.

**The GPU grades, as it shows.** The processor would take seconds for 11 million pixels. The grade is numbers beside the file: the file is never changed.

**Do once what does not change.** Interleaving the quilt again for each step took 70 ms on the Pi. So the interleaving is kept, and the colour tools go through a table of 33 x 33 x 33 colours. Measured on a Pi 5, with the request: 14 ms for light and colour, 31 ms with sharpness, shadows and the like, and 0.6 seconds once, when one of these is first used.

**Each view is filtered alone.** A blur that crossed into the next view would mix two directions.

**Limits for black skies.** StepIt Grader's sharpness and detail measure edges in stops. Next to pure black, an edge is many stops, and objects got a bright rim. We added a floor and a limit. These two tools differ from StepIt Grader on purpose.

**One button, Grade…, beside Black.** It grades the quilt on the screen, which is the row selected in the library. It is off for a video, the test pattern and a screen without the GPU, and says why.

**The grading page hides the panels.** If it removed them, an upload under way would stop.

**The server keeps the grade.** In the library's index, written a second after the last change, as a slider would wear the SD card.

**A `PUT` per step, one at a time, the newest next.** No WebSocket: the API stays REST, and the Pi's drawing is the limit.

**Save as new quilt.** It makes a new file, and never touches the original. The whole quilt goes through the same shaders, so it looks the same as while grading. It is a PNG: nothing is lost a second time. The name gets `-graded` before the layout.

**A save is `POST /api/media/{id}/graded-copies`.** It creates a resource, so it is a POST on a plural noun, with `201` and a `Location`. It has no body: the page waits until its last change has reached the server.

**The server lists the tools.** The page draws its sliders from `GET /api/grade-parameters`, so a new tool needs no change to the page.

## Left Out

Videos. The light and colour tools would cost a video little, as they are one table. The ones that look around a pixel would not keep up with its frames.

A picture of the result on the page, a histogram, copying a grade to another quilt.

Noise reduction, chromatic aberration, HDR compression and the sharpness's radius.

## Open Items

On the Portrait, over the network, a step takes 17 ms, or 33 with the tools that look around a pixel. How it looks through the lenses is still to be judged.
