// Moving through a list one item at a time, as the library's rows do with the arrow keys.

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
