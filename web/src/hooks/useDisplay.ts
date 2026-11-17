// The display's view model: what the Looking Glass shows, as useDisplayPolling last read it, and the commands to
// show a medium, the test pattern, or black. Used by the display panel and the library's play buttons.
import { useState } from 'react';
import { useHoloPiStore } from '../model/HoloPiStoreContext';
import { useServices } from '../services/ServicesContext';
import type { Result } from '../utils/result';

export function useDisplay() {
  const { state, dispatch } = useHoloPiStore();
  const { api } = useServices();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function run(command: () => Promise<Result<unknown>>) {
    if (pending) return;  // One command at a time: the screen changes once.
    setPending(true);
    setError(null);
    const result = await command();
    setPending(false);
    if (!result.ok) setError(result.error);
    const display = await api.getDisplay();
    if (display.ok) dispatch({ type: 'displayRead', display: display.value });
  }

  return {
    display: state.display,
    error,
    pending,
    play: (id: string) => run(() => api.showMedium(id)),
    showTestPattern: () => run(() => api.showTestPattern()),
    showBlack: () => run(() => api.showBlack()),
  };
}
