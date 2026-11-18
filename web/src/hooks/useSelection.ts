// Which items of a list are ticked, e.g. the library's media to remove in one go. The ticks are kept by id, and only
// those of items still in the list count, so an item removed or gone from the server is never selected. Used by the
// library panel.
import { useState } from 'react';

export function useSelection(ids: string[]) {
  const [ticked, setTicked] = useState<ReadonlySet<string>>(new Set());

  // Derived from the list, never stored: an id no longer in it drops out by itself.
  const selected = ids.filter(id => ticked.has(id));

  function toggle(id: string, on: boolean) {
    setTicked(previous => {
      const next = new Set(previous);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  function selectAll(on: boolean) {
    setTicked(on ? new Set(ids) : new Set());
  }

  return { selected, toggle, selectAll };
}
