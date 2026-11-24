# Mark the Graded Quilts

Branch `graded-badge`.

## Goal

A graded quilt looks the same as any other in the library. We want to see which ones are graded without opening the grading page of each.

## Decisions

**A badge on the row.** "graded", in green, beside the name. The card of what the Looking Glass shows has a line for it too.

**Off is told apart from on.** **Show original** stays on after we leave the grading page. The quilt is then shown without its grade, which is easy to forget. Its badge is "grade off", in grey.

**The medium says it: `grade`, `"on"`, `"off"` or `null`.** The page would otherwise ask for every quilt's grade to draw the list. The values stay at `/api/media/{id}/grade`, as no list needs them.

**A quilt is graded when one value differs from its default.** It is the same rule as the one that enables **Reset** on the grading page. A grade reset, or switched off with nothing in it, has no badge.

**The page marks it once the server has the change.** The library is hidden while grading, not read again. So the grading page tells the store, after each change the server took. A change it refused marks nothing.

**No more "on screen" badge.** The row of the medium shown has a colour of its own, and is almost always the selected one. The badge said it again, and crowded the new one.

## Left Out

A badge for the quilts saved with **Save as new quilt**. Their grade is in their pixels, and their name has `-graded`.

A change made elsewhere, e.g. with `curl`, shows on the display's card within 2 seconds, but in the library only after **Refresh**, as any other change to the list.
