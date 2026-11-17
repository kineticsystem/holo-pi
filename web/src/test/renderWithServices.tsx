// The composition root of the tests: the store, and fake services.
import type { ReactNode } from 'react';
import { HoloPiStoreProvider } from '../model/HoloPiStoreContext';
import { ServicesProvider, type Services } from '../services/ServicesContext';
import { FakeHoloPiApi } from './FakeHoloPiApi';

export class MemoryStorage {
  values = new Map<string, string>();
  getItem(key: string) {
    return this.values.get(key) ?? null;
  }
  setItem(key: string, value: string) {
    this.values.set(key, value);
  }
}

export function makeWrapper(overrides: Partial<Services> = {}) {
  const services: Services = { api: new FakeHoloPiApi(), storage: new MemoryStorage(), ...overrides };
  return ({ children }: { children: ReactNode }) => (
    <ServicesProvider value={services}><HoloPiStoreProvider>{children}</HoloPiStoreProvider></ServicesProvider>
  );
}
