// The services the page uses, given by App, the composition root, and by the tests with fakes.
import { createContext, useContext } from 'react';
import type { HoloPiApi } from './HoloPiApi';

export type Services = {
  api: HoloPiApi;
  /** The browser's storage, or an in-memory one in the tests. */
  storage: Pick<Storage, 'getItem' | 'setItem'>;
};

const ServicesContext = createContext<Services | null>(null);
export const ServicesProvider = ServicesContext.Provider;

export function useServices(): Services {
  const services = useContext(ServicesContext);
  if (!services) throw new Error('useServices() outside <ServicesProvider>');
  return services;
}
