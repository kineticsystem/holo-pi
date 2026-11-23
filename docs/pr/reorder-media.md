# Order the Library by Dragging

Branch `reorder-media`.

## Goal

The library lists the media in the order they were uploaded. We want to put them in our own order: grab a row and move it.

## Decisions

**The server keeps the order.** The order of `index.json` is the library's order. The page, `curl` and every browser see the same one, and it stays after a restart.

**`PUT /api/media/order` takes the whole order.** The body is every id of the library, once: `{"ids": [...]}`. Sending it twice changes nothing, unlike a "move this one to place 3", which depends on the list the client saw. It is a singleton under the collection, as the API's rules want: no verb in the path.

**A list that misses an id is refused.** If another client uploaded or removed a medium meanwhile, the server answers `400` or `404` rather than guess where the others go. The page then reads the list again and says why.

**A replacement keeps its place.** An upload of a name the library has kept its id, but went last. Now it stays where it was; a new upload still goes last.

**A grip on each row, and the whole row follows.** Only the grip, ⠿, starts a drag, so that the links, buttons and boxes of a row keep their own job, and a click on the row still shows it. The upper half of a row drops above it, the lower half below; a line shows where.

**The browser's own drag and drop, no library.** The page has no dependency besides React. A drag from outside the table, e.g. a file for the upload, is not a move.

**Alt and the arrow keys move the current row.** The arrows alone show the row above or below; with Alt, the current row moves past its neighbour. A keyboard can do what the mouse does.

**The page moves the row at once.** The store takes the new order before the server answers. The answer of an order that a newer one overtook is dropped.

## Left Out

Dragging several ticked rows together. One row at a time is enough for now.

Touch screens: the browser's drag and drop does not start from a finger on most phones. Alt and the arrow keys need a keyboard too.

## Open Items

The browser automation cannot start a native drag, so the drag was checked in Chrome with real `DragEvent`s sent from the page: the line showed, the row moved, and the server kept the order. A drag by hand is still worth a try on the Pi.
