// The library's media, one row each, with what they are, buttons to download and remove them, and a box to tick
// each, to remove several in one go. A click on a row shows its medium, and the arrow keys show the one above or below.
import type { KeyboardEvent, MouseEvent } from 'react';
import type { Medium } from '../services/HoloPiApi';
import { formatBytes, formatDuration, formatLayout, formatTime } from '../utils/formatUtils';
import { stepThrough } from '../utils/listUtils';
import { ConfirmButton } from './ConfirmButton';

type MediaTableProps = {
  media: Medium[];
  shownId: string | null;
  /** The row the arrow keys go on from: the medium asked for last, or the one on the screen. */
  currentId: string | null;
  selected: string[];
  disabled: boolean;
  contentUrl: (id: string) => string;
  onShow: (id: string) => void;
  onRemove: (id: string) => void;
  onSelect: (id: string, on: boolean) => void;
  onSelectAll: (on: boolean) => void;
};

const STEPS: Record<string, 1 | -1> = { ArrowDown: 1, ArrowUp: -1 };

export function MediaTable({ media, shownId, currentId, selected, disabled, contentUrl, onShow, onRemove, onSelect,
                            onSelectAll }: MediaTableProps) {
  if (media.length === 0) return <p className="empty">The library is empty: upload a quilt or a video.</p>;
  const allSelected = selected.length === media.length;
  const someSelected = selected.length > 0 && !allSelected;

  function handleKeyDown(event: KeyboardEvent<HTMLTableElement>) {
    const step = STEPS[event.key];
    if (!step) return;
    event.preventDefault();  // The arrows move through the rows, not the page.
    const id = stepThrough(media.map(medium => medium.id), currentId, step);
    if (id === null || id === currentId) return;
    onShow(id);
    event.currentTarget.querySelector(`tr[data-id="${id}"]`)?.scrollIntoView?.({ block: 'nearest' });
  }

  function handleRowClick(event: MouseEvent<HTMLTableRowElement>, id: string) {
    if ((event.target as HTMLElement).closest('input, a, button')) return;  // The row's own controls do their own job.
    onShow(id);
  }

  return (
    <table className="media" tabIndex={0} aria-label="Library: click a row or use the arrow keys to show it"
           onKeyDown={handleKeyDown}>
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
          <tr key={medium.id} data-id={medium.id} aria-current={medium.id === currentId ? 'true' : undefined}
              className={[medium.id === shownId && 'shown', medium.id === currentId && 'current'].filter(Boolean).join(' ')}
              onClick={event => handleRowClick(event, medium.id)}>
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
