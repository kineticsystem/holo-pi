// The library's media, one row each, with what they are and buttons to play, download and remove them.
import type { Medium } from '../services/HoloPiApi';
import { formatBytes, formatDuration, formatLayout, formatTime } from '../utils/formatUtils';
import { ConfirmButton } from './ConfirmButton';

type MediaTableProps = {
  media: Medium[];
  shownId: string | null;
  disabled: boolean;
  contentUrl: (id: string) => string;
  onPlay: (id: string) => void;
  onRemove: (id: string) => void;
};

export function MediaTable({ media, shownId, disabled, contentUrl, onPlay, onRemove }: MediaTableProps) {
  if (media.length === 0) return <p className="empty">The library is empty: upload a quilt or a video.</p>;
  return (
    <table className="media">
      <thead>
        <tr>
          <th>Name</th><th>Kind</th><th>Layout</th><th>Size</th><th>Length</th><th>Uploaded</th><th />
        </tr>
      </thead>
      <tbody>
        {media.map(medium => (
          <tr key={medium.id} className={medium.id === shownId ? 'shown' : undefined}>
            <td>
              <span className="name">{medium.name}</span>
              {medium.id === shownId && <span className="badge">on screen</span>}
              {medium.warning && <span className="badge warning" title={medium.warning}>not H.265</span>}
              <div className="id">{medium.id}</div>
            </td>
            <td>{medium.kind}</td>
            <td>{formatLayout(medium.columns, medium.rows)}</td>
            <td>{formatBytes(medium.size)}</td>
            <td>{formatDuration(medium.duration)}{medium.fps ? ` · ${Math.round(medium.fps)} fps` : ''}</td>
            <td>{formatTime(medium.uploaded)}</td>
            <td>
              <div className="actions">
                <button className="primary" disabled={disabled} onClick={() => onPlay(medium.id)}>Play</button>
                <a className="button" href={contentUrl(medium.id)} download={medium.name}>Download</a>
                <ConfirmButton label="Remove" confirmLabel="Remove it" disabled={disabled}
                               onConfirm={() => onRemove(medium.id)} />
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
