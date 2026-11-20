// The display's view model: what the Looking Glass shows, as useDisplayPolling last read it, and the commands to
// show a medium, the test pattern, or black. Used by the display panel and the library's rows.
import { useRef, useState } from 'react';
import { useHoloPiStore } from '../model/HoloPiStoreContext';
import { useServices } from '../services/ServicesContext';
import type { Result } from '../utils/result';

type Command = () => Promise<Result<unknown>>;

export function useDisplay() {
  const { state, dispatch } = useHoloPiStore();
  const { api } = useServices();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  // The medium asked for last, until the screen has it: where the arrow keys go on from, ahead of the display.
  const [wanted, setWanted] = useState<string | null>(null);
  const runningRef = useRef(false);
  const nextRef = useRef<Command | null>(null);

  // One command at a time, the newest next: arrowing through the library sends the medium it stops on, not each one
  // it passes, and every press counts, even while the screen is still changing.
  async function run(command: Command) {
    if (runningRef.current) {
      nextRef.current = command;
      return;
    }
    runningRef.current = true;
    setPending(true);
    let next: Command | null = command;
    while (next) {
      nextRef.current = null;
      const result = await next();
      setError(result.ok ? null : result.error);
      if (nextRef.current === null) {
        const display = await api.getDisplay();
        if (display.ok) dispatch({ type: 'displayRead', display: display.value });
      }
      next = nextRef.current;
    }
    runningRef.current = false;
    setPending(false);
    setWanted(null);
  }

  return {
    display: state.display,
    error,
    pending,
    wanted,
    show: (id: string) => {
      setWanted(id);
      return run(() => api.showMedium(id));
    },
    showTestPattern: () => {
      setWanted(null);
      return run(() => api.showTestPattern());
    },
    showBlack: () => {
      setWanted(null);
      return run(() => api.showBlack());
    },
  };
}
