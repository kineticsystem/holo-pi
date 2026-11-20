// The composition root of the tests: the store, and fake services.
import type { ReactNode } from 'react';
import { HoloPiStoreProvider } from '../model/HoloPiStoreContext';
import { ServicesProvider, type Services } from '../services/ServicesContext';
import { FakeHoloPiApi } from './FakeHoloPiApi';

export function makeWrapper(overrides: Partial<Services> = {}) {
  const services: Services = { api: new FakeHoloPiApi(), ...overrides };
  return ({ children }: { children: ReactNode }) => (
    <ServicesProvider value={services}><HoloPiStoreProvider>{children}</HoloPiStoreProvider></ServicesProvider>
  );
}
