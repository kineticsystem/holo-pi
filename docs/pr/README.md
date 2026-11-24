# Pull Request Notes

Each pull request has a notes file here. It keeps what the pull request does not: what we discussed, what we chose, and why.

## The Notes

| Note | Pull request |
|---|---|
| [5-mermaid-diagrams.md](5-mermaid-diagrams.md) | [#5](https://github.com/kineticsystem/holo-pi/pull/5) Diagrams as SVG images, from Mermaid sources |
| [6-video-playback.md](6-video-playback.md) | [#6](https://github.com/kineticsystem/holo-pi/pull/6) Videos on the GPU, a library, a REST API and a web page |
| [9-remove-selected.md](9-remove-selected.md) | [#9](https://github.com/kineticsystem/holo-pi/pull/9) Remove several media in one go |
| [10-revert-play-then.md](10-revert-play-then.md) | [#10](https://github.com/kineticsystem/holo-pi/pull/10) Revert of #8, a video once, then another in a loop |
| [11-darker-quilts.md](11-darker-quilts.md) | [#11](https://github.com/kineticsystem/holo-pi/pull/11) Darker quilts: a black sky, a grade, true mirrors, and no spheres |
| [12-click-to-show.md](12-click-to-show.md) | [#12](https://github.com/kineticsystem/holo-pi/pull/12) Web page: click a row to show it, the arrow keys to go up and down |
| [13-upload-shows-first.md](13-upload-shows-first.md) | [#13](https://github.com/kineticsystem/holo-pi/pull/13) Uploads always show the first file; no reverse box |
| [14-web-page-screenshot.md](14-web-page-screenshot.md) | [#14](https://github.com/kineticsystem/holo-pi/pull/14) README: the web page's screenshot as it is now |
| [15-reorder-media.md](15-reorder-media.md) | [#15](https://github.com/kineticsystem/holo-pi/pull/15) Order the library by dragging a row |
| [16-quilt-grading.md](16-quilt-grading.md) | [#16](https://github.com/kineticsystem/holo-pi/pull/16) Grade a quilt while the Looking Glass shows it, and rename a medium |

## How to Write One

- One file per pull request: `<number>-<branch>.md`, e.g. `5-mermaid-diagrams.md`. Before it has a number, use the branch name.
- Sections: **Goal**, **Decisions**, **Left Out**, **Open Items**. Skip the ones that do not apply.
- Short sentences. One idea per paragraph. A diagram when it explains faster.
- Write it while the branch is open. Do not rewrite it after the merge.
