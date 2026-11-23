// Moving through a list one item at a time, as the library's rows do with the arrow keys, and moving an item
// to another place, as dragging a row does.

/**
 * The id `step` places away from `current` in `ids`, stopping at the ends: the first or the last when `current` is
 * not in the list, e.g. nothing shown yet, and null when the list is empty.
 */
export function stepThrough(ids: string[], current: string | null, step: 1 | -1): string | null {
  if (ids.length === 0) return null;
  const index = current === null ? -1 : ids.indexOf(current);
  if (index === -1) return step === 1 ? ids[0] : ids[ids.length - 1];
  return ids[Math.min(Math.max(index + step, 0), ids.length - 1)];
}

/**
 * `ids` with `moved` taken out and put back next to `target`: just before it, or just after it with `after`. The same
 * order when either is not in the list, or they are the same.
 */
export function moveNextTo(ids: string[], moved: string, target: string, after: boolean): string[] {
  if (moved === target || !ids.includes(moved) || !ids.includes(target)) return ids;
  const others = ids.filter(id => id !== moved);
  const index = others.indexOf(target) + (after ? 1 : 0);
  return [...others.slice(0, index), moved, ...others.slice(index)];
}

/** Whether two lists of ids are in the same order. */
export function sameOrder(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((id, index) => id === b[index]);
}
