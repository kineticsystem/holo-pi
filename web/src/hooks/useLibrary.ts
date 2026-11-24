// The library's view model: the media, the space they take, which one is shown, and the commands to read the list
// again, put it in another order, rename one, remove one, several, or them all. Used by the library panel.
import { useCallback, useEffect, useRef, useState } from 'react';
import { selectShownId } from '../model/holoPiStore';
import { useHoloPiStore } from '../model/HoloPiStoreContext';
import { useServices } from '../services/ServicesContext';

export function useLibrary() {
  const { state, dispatch } = useHoloPiStore();
  const { api } = useServices();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const orderRef = useRef(0);  // The number of the last order asked for: an older answer is stale.

  const refresh = useCallback(async (signal?: AbortSignal) => {
    const result = await api.listMedia(signal);
    if (signal?.aborted) return;
    if (result.ok) {
      dispatch({ type: 'mediaListed', list: result.value });
      setError(null);
    } else {
      setError(result.error);
    }
  }, [api, dispatch]);

  // The list, from the server, when the page opens.
  useEffect(() => {
    const controller = new AbortController();
    void refresh(controller.signal);
    return () => controller.abort();
  }, [refresh]);

  // One after another: those the server removes leave the list, those it refuses stay, and the page says why.
  async function removeMany(ids: string[]) {
    if (ids.length === 0) return;
    setBusy(true);
    const failures: string[] = [];
    for (const id of ids) {
      const result = await api.removeMedium(id);
      if (result.ok) dispatch({ type: 'mediumRemoved', id });
      else failures.push(result.error);
    }
    setBusy(false);
    if (failures.length > 0) {
      setError(ids.length === 1 ? failures[0] : `${failures.length} of ${ids.length} not removed: ${failures[0]}`);
    }
    if (failures.length < ids.length) await refreshDisplay();
  }

  // The new order shows at once; the server's answer then replaces the list, unless another order came after it. If
  // the server refuses it, e.g. a medium came or went meanwhile, the page says why and reads the list again.
  async function reorder(ids: string[]) {
    const number = ++orderRef.current;
    dispatch({ type: 'mediaOrdered', ids });
    const result = await api.orderMedia(ids);
    if (number !== orderRef.current) return;
    if (result.ok) {
      dispatch({ type: 'mediaListed', list: result.value });
      setError(null);
    } else {
      await refresh();
      setError(result.error);
    }
  }

  // Whether it went: a name the server refuses, e.g. another medium's, stays to be corrected.
  async function rename(id: string, name: string): Promise<boolean> {
    const result = await api.renameMedium(id, name);
    if (!result.ok) {
      setError(result.error);
      return false;
    }
    setError(null);
    dispatch({ type: 'mediumRenamed', medium: result.value });
    if (selectShownId(state) === id) await refreshDisplay(); // It says the name too.
    return true;
  }

  async function removeAll() {
    if (!state.media?.length) return;
    setBusy(true);
    const result = await api.removeAllMedia();
    setBusy(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    dispatch({ type: 'allMediaRemoved' });
    await refreshDisplay();
  }

  // Removing the medium shown shows black, and renaming it changes its name there: the display says so at once.
  async function refreshDisplay() {
    const display = await api.getDisplay();
    if (display.ok) dispatch({ type: 'displayRead', display: display.value });
  }

  return {
    media: state.media,
    size: state.size,
    free: state.free,
    shownId: selectShownId(state),
    loading: state.media === null && error === null,
    busy,
    error,
    refresh: () => refresh(),
    remove: (id: string) => removeMany([id]),
    removeMany,
    removeAll,
    reorder,
    rename,
    contentUrl: api.contentUrl,
  };
}
