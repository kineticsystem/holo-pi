# Remove Several Media in One Go

Pull request [#9](https://github.com/kineticsystem/holo-pi/pull/9), branch `remove-selected`.

## Goal

Remove several quilts and videos of the library at once from the web page, without removing them one by one and without emptying the whole library.

## Decisions

**A box to tick on each row, and one in the header.** The header's box selects all or none, and shows a dash when only some are ticked. "Remove selected (n)", next to "Remove all", asks again before it acts, like every removal of the page.

**No change to the API.** The page sends one `DELETE /api/media/{id}` per medium, one after another. A library holds tens of media, not thousands, and each removal is quick, so a new route for many ids would add an API to document and test for no gain.

**A removal refused does not stop the others.** Those the server removes leave the list; those it refuses stay, still ticked, and the page says how many failed and why, e.g. `1 of 3 not removed: ...`. Removing one medium is the same command with one id.

**The ticks are derived from the list.** `useSelection` keeps the ids ticked, but `selected` is only those still in the library. A medium removed, or gone after a refresh, drops out by itself, with no effect to keep the two in step.

## Left Out

The screenshot of the web page, `docs/images/web-page.png`, does not show the boxes yet.
