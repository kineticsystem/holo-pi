// The page the browser's address asks for. Used by App.
import { useSyncExternalStore } from 'react';
import { parseRoute, type Route } from '../utils/routeUtils';

function subscribe(onChange: () => void) {
  window.addEventListener('hashchange', onChange);
  return () => window.removeEventListener('hashchange', onChange);
}

export function useRoute(): Route {
  return parseRoute(useSyncExternalStore(subscribe, () => window.location.hash));
}
