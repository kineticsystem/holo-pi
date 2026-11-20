# Uploads Always Show the First File

Pull request [#13](https://github.com/kineticsystem/holo-pi/pull/13), branch `upload-shows-first`.

## Goal

Upload from the web page with nothing to choose but a layout: what we upload, we see. It was pushed to `click-to-show` after #12 was merged, and comes here instead.

## Decisions

**An upload always shows the first file.** One file dropped is shown as soon as it is in; of several, the first, and the others are only kept. Showing each in turn would end on the last. The box "Show it at once" went.

**No "Views in reverse" on the page.** A quilt whose depth looks inside out is rare, and `reverse` stays in the API for it: `curl -F reverse=true`. The page asks only the layout, `UploadLayout`, when the name does not give it.

**No storage in the page.** The box's last choice was the only value the page kept in the browser, so `usePersistentState`, `utils/storageKeys.ts` and the `storage` service went with it.

**The API does not change.** `play` and `reverse` stay, for `curl` and scripts; only the page stops offering them.
