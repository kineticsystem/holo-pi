// The composition root: the one place that names the real services, then the store and the page's panels.
import { Tabs } from '../components/Tabs';
import { DisplayPanel } from '../features/DisplayPanel';
import { ErrorBoundary } from '../features/ErrorBoundary';
import { GradePage } from '../features/GradePage';
import { Header } from '../features/Header';
import { LibraryPanel } from '../features/LibraryPanel';
import { PlayPanel } from '../features/PlayPanel';
import { useDisplayPolling } from '../hooks/useDisplayPolling';
import { useRoute } from '../hooks/useRoute';
import { UploadPanel } from '../features/UploadPanel';
import { HoloPiStoreProvider } from '../model/HoloPiStoreContext';
import { makeHttpHoloPiApi } from '../services/httpHoloPiApi';
import { ServicesProvider, type Services } from '../services/ServicesContext';
import { formatRoute } from '../utils/routeUtils';

const TABS = [
  { label: 'Library', href: formatRoute({ page: 'library' }) },
  { label: 'Play', href: formatRoute({ page: 'play' }) },
];

const services: Services = { api: makeHttpHoloPiApi() };

/** The page's background work, mounted once inside the providers: what the Looking Glass shows, kept fresh. */
function Background() {
  useDisplayPolling();
  return null;
}

export function App() {
  const route = useRoute();
  return (
    <ServicesProvider value={services}>
      <HoloPiStoreProvider>
        <Background />
        <ErrorBoundary name="header"><Header /></ErrorBoundary>
        {route.page === 'grade' && (
          <ErrorBoundary key={route.id} name="grading page"><GradePage id={route.id} /></ErrorBoundary>
        )}
        {/* Hidden while grading, not gone, so that the uploads go on. */}
        <main hidden={route.page === 'grade'}>
          <div className="side">
            <ErrorBoundary name="display panel"><DisplayPanel /></ErrorBoundary>
            <ErrorBoundary name="upload panel"><UploadPanel /></ErrorBoundary>
          </div>
          <div className="tabbed">
            <Tabs tabs={TABS} current={formatRoute(route)} />
            {route.page === 'play'
              ? <ErrorBoundary key="play" name="play tab"><PlayPanel /></ErrorBoundary>
              : <ErrorBoundary key="library" name="library"><LibraryPanel /></ErrorBoundary>}
          </div>
        </main>
      </HoloPiStoreProvider>
    </ServicesProvider>
  );
}
