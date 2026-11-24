# Copy a Grade from Another Quilt

Branch `copy-grade`.

## Goal

We want the look of one quilt on another, from the web page. Until now it took two requests with `curl`.

## Decisions

**A list on the grading page, not copy and paste.** The medium already says whether it is graded, so the page can list the quilts to copy from. A clipboard would be a state to keep, and to forget, between two pages.

**The result shows at once.** Choosing a quilt is a change like any other: the sliders move, the Looking Glass follows, the server keeps it. So looks can be compared by choosing one after another.

**Undo, rather than asking twice.** A copy replaces the whole grade. A question at each try would be in the way of comparing. **Undo copy** goes back to the grade from before the first copy. **Show original** does not end it, as it only compares. Any other change does.

**A grade that is off is copied on.** To copy it is to want to see it.

**The values come from the server when copied.** Not from what the page knew. If the other quilt was reset meanwhile, the page says so, and does not reset this one.

**A late answer is dropped.** After a slider moved, another quilt was chosen, or the page was left.

**The page reads the library again when it opens.** Another browser may have graded a quilt. It does so before the sliders show, as a list read later could miss a change made here.

**No change to the API.** A `GET` of one grade and a `PUT` of the other is all it takes.

## Left Out

Copying to several quilts at once. It could be a button above the library, for the ticked quilts.

Copying some sections only, e.g. Light.

## Open Items

The README's picture of the grading page is older than **Copy grade from…**, and is to be taken again on a Pi.
