// The store, given to the page through a Context: useReducer, with no store library.
import { createContext, useContext, useReducer, type Dispatch, type ReactNode } from 'react';
import { holoPiReducer, initialState, type HoloPiAction, type HoloPiState } from './holoPiStore';

type Store = { state: HoloPiState; dispatch: Dispatch<HoloPiAction> };

const StoreContext = createContext<Store | null>(null);

export function HoloPiStoreProvider({ children, initial = initialState }: { children: ReactNode; initial?: HoloPiState }) {
  const [state, dispatch] = useReducer(holoPiReducer, initial);
  return <StoreContext.Provider value={{ state, dispatch }}>{children}</StoreContext.Provider>;
}

export function useHoloPiStore(): Store {
  const store = useContext(StoreContext);
  if (!store) throw new Error('useHoloPiStore() outside <HoloPiStoreProvider>');
  return store;
}
