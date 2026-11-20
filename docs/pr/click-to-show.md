# Click a Row to Show It

Branch `click-to-show`.

## Goal

Show a medium of the library without a play button: a click on its row shows it, and the arrow keys show the one above or below, so that we can go through the library from the keyboard.

## Decisions

**No play button.** A click anywhere on a row shows its medium. The row's own controls, the box to tick, Download and Remove, keep their own job and do not show it.

**The arrow keys on the table.** The table takes the focus, with a click on a row or with Tab. Down and up show the next or the previous medium, and stop at the ends; with nothing shown, down starts at the first and up at the last. The page does not scroll with them, and the row reached scrolls into view.

**The arrows go on from the medium asked for, not the one on the screen.** Showing a medium takes from 0.2 to 0.8 seconds on a Pi 5. Going on from what the screen shows would make a quick second press repeat the first. `useDisplay` keeps `wanted`, the medium asked for last, until the screen has it; the table marks that row with a bar on its left, and the one on the screen keeps its colour and its "on screen" badge.

**One command at a time, the newest next.** Before, a command sent while another ran was dropped, so a quick press did nothing. Now the newest waits and the ones in between are skipped: three quick presses send the first medium and the last, not the middle one. The page asks what is shown once, after the last.

**`stepThrough()` in `utils/listUtils.ts`.** Which id is next is a pure function, tested without a table.

## Left Out

The screenshot of the web page, `docs/images/web-page.png`, still shows the play buttons.
