// The library's view model: the media, the space they take, which one is shown, and the commands to read the list
// again, remove one, or remove them all. Used by the library panel.
import { useCallback, useEffect, useState } from 'react';
import { selectShownId } from '../model/holoPiStore';
import { useHoloPiStore } from '../model/HoloPiStoreContext';
import { useServices } from '../services/ServicesContext';

export function useLibrary() {
  const { state, dispatch } = useHoloPiStore();
  const { api } = useServices();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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

  async function remove(id: string) {
    setBusy(true);
    const result = await api.removeMedium(id);
    setBusy(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    dispatch({ type: 'mediumRemoved', id });
    await refreshDisplay();
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

  // Removing the medium shown shows black: the display says so at once.
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
    remove,
    removeAll,
    contentUrl: api.contentUrl,
  };
}
