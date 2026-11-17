// The composition root: the one place that names the real services, then the store and the page's panels.
import { DisplayPanel } from '../features/DisplayPanel';
import { ErrorBoundary } from '../features/ErrorBoundary';
import { Header } from '../features/Header';
import { LibraryPanel } from '../features/LibraryPanel';
import { useDisplayPolling } from '../hooks/useDisplayPolling';
import { UploadPanel } from '../features/UploadPanel';
import { HoloPiStoreProvider } from '../model/HoloPiStoreContext';
import { makeHttpHoloPiApi } from '../services/httpHoloPiApi';
import { ServicesProvider, type Services } from '../services/ServicesContext';

const services: Services = { api: makeHttpHoloPiApi(), storage: window.localStorage };

/** The page's background work, mounted once inside the providers: what the Looking Glass shows, kept fresh. */
function Background() {
  useDisplayPolling();
  return null;
}

export function App() {
  return (
    <ServicesProvider value={services}>
      <HoloPiStoreProvider>
        <Background />
        <ErrorBoundary name="header"><Header /></ErrorBoundary>
        <main>
          <div className="side">
            <ErrorBoundary name="display panel"><DisplayPanel /></ErrorBoundary>
            <ErrorBoundary name="upload panel"><UploadPanel /></ErrorBoundary>
          </div>
          <ErrorBoundary name="library"><LibraryPanel /></ErrorBoundary>
        </main>
      </HoloPiStoreProvider>
    </ServicesProvider>
  );
}
