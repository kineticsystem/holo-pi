// The page's header: the server's version, the Looking Glass, and the link to the API's documentation.
import { useServerStatus } from '../hooks/useServerStatus';

export function Header() {
  const { status, docsUrl } = useServerStatus();
  const glass = status?.looking_glass;
  return (
    <header>
      <h1>HoloPi</h1>
      <span className="glass">
        {glass ? `${glass.serial}, ${glass.width} × ${glass.height}` : status?.calibration_error ?? ''}
      </span>
      <span className="version">{status ? `v${status.version}, screen ${status.screen}` : ''}</span>
      <a href={docsUrl} target="_blank" rel="noreferrer">API documentation</a>
    </header>
  );
}
