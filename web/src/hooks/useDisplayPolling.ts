// Asks the server what the Looking Glass shows every POLL_MS, so that a video's frame rate, an unplugged Looking
// Glass, or a change made elsewhere, e.g. with curl, show on the page. Mounted once, by App.
import { useEffect } from 'react';
import { useHoloPiStore } from '../model/HoloPiStoreContext';
import { useServices } from '../services/ServicesContext';

/** How often the page asks what the Looking Glass shows. */
export const POLL_MS = 2000;

export function useDisplayPolling() {
  const { dispatch } = useHoloPiStore();
  const { api } = useServices();

  useEffect(() => {
    let controller = new AbortController();
    async function read() {
      const result = await api.getDisplay(controller.signal);
      if (!controller.signal.aborted && result.ok) dispatch({ type: 'displayRead', display: result.value });
    }
    void read();
    const timer = setInterval(() => {
      controller.abort(); // A read still waiting is out of date.
      controller = new AbortController();
      void read();
    }, POLL_MS);
    return () => {
      clearInterval(timer);
      controller.abort();
    };
  }, [api, dispatch]);
}
