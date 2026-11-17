// The library: the media kept on the Raspberry Pi, to play, download or remove, and the space left.
import { ConfirmButton } from '../components/ConfirmButton';
import { ErrorMessage } from '../components/ErrorMessage';
import { MediaTable } from '../components/MediaTable';
import { useDisplay } from '../hooks/useDisplay';
import { useLibrary } from '../hooks/useLibrary';
import { formatBytes } from '../utils/formatUtils';

export function LibraryPanel() {
  const library = useLibrary();
  const display = useDisplay();
  return (
    <section>
      <h2>Library</h2>
      <p className="totals">
        {library.media ? `${library.media.length} media, ${formatBytes(library.size)}; ` : ''}
        {formatBytes(library.free)} free
        <button onClick={() => void library.refresh()}>Refresh</button>
        <ConfirmButton label="Remove all" confirmLabel="Remove every medium" disabled={library.busy || !library.media?.length}
                       onConfirm={() => void library.removeAll()} />
      </p>
      {library.loading ? <p className="empty">Asking the server…</p> : (
        <MediaTable media={library.media ?? []} shownId={library.shownId} disabled={library.busy || display.pending}
                    contentUrl={library.contentUrl} onPlay={id => void display.play(id)}
                    onRemove={id => void library.remove(id)} />
      )}
      <ErrorMessage text={library.error ?? display.error} />
    </section>
  );
}
