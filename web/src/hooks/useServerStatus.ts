// The server's status, read when the page opens: its version, its screen and the Looking Glass. Used by the header.
import { useEffect } from 'react';
import { useHoloPiStore } from '../model/HoloPiStoreContext';
import { useServices } from '../services/ServicesContext';

export function useServerStatus() {
  const { state, dispatch } = useHoloPiStore();
  const { api } = useServices();

  useEffect(() => {
    const controller = new AbortController();
    void api.getStatus(controller.signal).then(result => {
      if (!controller.signal.aborted && result.ok) dispatch({ type: 'statusRead', status: result.value });
    });
    return () => controller.abort();
  }, [api, dispatch]);

  return { status: state.status, docsUrl: api.docsUrl };
}
