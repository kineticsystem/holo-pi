// The library's media, one row each, with what they are, buttons to play, download and remove them, and a box to tick
// each, to remove several in one go.
import type { Medium } from '../services/HoloPiApi';
import { formatBytes, formatDuration, formatLayout, formatTime } from '../utils/formatUtils';
import { ConfirmButton } from './ConfirmButton';

type MediaTableProps = {
  media: Medium[];
  shownId: string | null;
  selected: string[];
  disabled: boolean;
  contentUrl: (id: string) => string;
  onPlay: (id: string) => void;
  onRemove: (id: string) => void;
  onSelect: (id: string, on: boolean) => void;
  onSelectAll: (on: boolean) => void;
};

export function MediaTable({ media, shownId, selected, disabled, contentUrl, onPlay, onRemove, onSelect,
                            onSelectAll }: MediaTableProps) {
  if (media.length === 0) return <p className="empty">The library is empty: upload a quilt or a video.</p>;
  const allSelected = selected.length === media.length;
  const someSelected = selected.length > 0 && !allSelected;
  return (
    <table className="media">
      <thead>
        <tr>
          <th className="select">
            <input type="checkbox" aria-label="Select all" checked={allSelected} disabled={disabled}
                   ref={box => { if (box) box.indeterminate = someSelected; }}
                   onChange={event => onSelectAll(event.target.checked)} />
          </th>
          <th>Name</th><th>Kind</th><th>Layout</th><th>Size</th><th>Length</th><th>Uploaded</th><th />
        </tr>
      </thead>
      <tbody>
        {media.map(medium => (
          <tr key={medium.id} className={medium.id === shownId ? 'shown' : undefined}>
            <td className="select">
              <input type="checkbox" aria-label={`Select ${medium.name}`} checked={selected.includes(medium.id)}
                     disabled={disabled} onChange={event => onSelect(medium.id, event.target.checked)} />
            </td>
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
