# Revert: Play a Video Once, Then Another in a Loop

Branch `revert-play-then`.

## Goal

Undo pull request [#8](https://github.com/kineticsystem/holo-pi/pull/8): `PUT /api/display` no longer takes `then`, and `GET /api/display` no longer names the next video.

## Decisions

**A revert, not a rewrite of `main`.** `git revert -m 1` of #8's merge, `329f1dc`, adds a commit that undoes it. The history stays, and #8 can come back with a revert of this revert.

**#9 stays.** The removal of several media came after #8 and does not depend on it; the revert applied with no conflict.

## Open Items

Why #8 is rolled back, and whether it comes back changed.
