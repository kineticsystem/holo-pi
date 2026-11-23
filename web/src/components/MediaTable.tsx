// The library's media, one row each, with what they are, buttons to download and remove them, and a box to tick
// each, to remove several in one go. A click on a row shows its medium, and the arrow keys show the one above or below.
// A row moves by its grip, dragged above or below another, or with Alt and the arrow keys for the current row.
import { useState, type DragEvent, type KeyboardEvent, type MouseEvent } from 'react';
import type { Medium } from '../services/HoloPiApi';
import { formatBytes, formatDuration, formatLayout, formatTime } from '../utils/formatUtils';
import { moveNextTo, sameOrder, stepThrough } from '../utils/listUtils';
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
  /** The media's ids in the order wanted, after a row moved. */
  onMove: (ids: string[]) => void;
  onRemove: (id: string) => void;
  onSelect: (id: string, on: boolean) => void;
  onSelectAll: (on: boolean) => void;
};

const STEPS: Record<string, 1 | -1> = { ArrowDown: 1, ArrowUp: -1 };

type Drop = { id: string; after: boolean };

export function MediaTable({ media, shownId, currentId, selected, disabled, contentUrl, onShow, onMove, onRemove,
                            onSelect, onSelectAll }: MediaTableProps) {
  const [dragged, setDragged] = useState<string | null>(null);  // The row being dragged.
  const [drop, setDrop] = useState<Drop | null>(null);  // Where it would land: next to this row.
  if (media.length === 0) return <p className="empty">The library is empty: upload a quilt or a video.</p>;
  const ids = media.map(medium => medium.id);
  const allSelected = selected.length === media.length;
  const someSelected = selected.length > 0 && !allSelected;

  function move(moved: string, target: string, after: boolean) {
    const order = moveNextTo(ids, moved, target, after);
    if (!sameOrder(order, ids)) onMove(order);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTableElement>) {
    const step = STEPS[event.key];
    if (!step) return;
    event.preventDefault();  // The arrows move through the rows, not the page.
    const id = stepThrough(ids, currentId, step);
    if (id === null || id === currentId) return;
    if (event.altKey) {
      // Alt moves the current row past its neighbour, and it stays the current one.
      if (currentId !== null && ids.includes(currentId)) move(currentId, id, step === 1);
    } else {
      onShow(id);
    }
    event.currentTarget.querySelector(`tr[data-id="${id}"]`)?.scrollIntoView?.({ block: 'nearest' });
  }

  function handleRowClick(event: MouseEvent<HTMLTableRowElement>, id: string) {
    // The row's own controls, and its grip, do their own job.
    if ((event.target as HTMLElement).closest('input, a, button, .grip')) return;
    onShow(id);
  }

  function handleDragStart(event: DragEvent<HTMLElement>, id: string) {
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', id);  // Firefox drags only with some data.
    const row = event.currentTarget.closest('tr');
    if (row) event.dataTransfer.setDragImage?.(row, 16, row.offsetHeight / 2);  // The whole row follows the pointer.
    setDragged(id);
  }

  // Over the upper half of a row, it lands above; over the lower half, below.
  function handleDragOver(event: DragEvent<HTMLTableRowElement>, id: string) {
    if (dragged === null) return;  // Not one of our rows, e.g. a file: the upload's drop zone takes those.
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
    const box = event.currentTarget.getBoundingClientRect();
    const after = event.clientY > box.top + box.height / 2;
    if (drop?.id !== id || drop.after !== after) setDrop({ id, after });
  }

  function handleDrop(event: DragEvent<HTMLTableRowElement>) {
    if (dragged === null) return;
    event.preventDefault();
    if (drop) move(dragged, drop.id, drop.after);
    endDrag();
  }

  function endDrag() {
    setDragged(null);
    setDrop(null);
  }

  function rowClass(id: string) {
    return [id === shownId && 'shown', id === currentId && 'current', id === dragged && 'dragging',
            drop?.id === id && dragged !== id && (drop.after ? 'drop-after' : 'drop-before')].filter(Boolean).join(' ');
  }

  return (
    <table className="media" tabIndex={0}
           aria-label="Library: click a row or use the arrow keys to show it; drag its grip, or Alt and the arrow keys, to move it"
           onKeyDown={handleKeyDown}>
      <thead>
        <tr>
          <th className="grip" />
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
              className={rowClass(medium.id)} onClick={event => handleRowClick(event, medium.id)}
              onDragOver={event => handleDragOver(event, medium.id)} onDrop={handleDrop}>
            <td className="grip">
              <span draggable aria-label={`Move ${medium.name}`} title="Drag to move; or Alt and the arrow keys"
                    onDragStart={event => handleDragStart(event, medium.id)} onDragEnd={endDrag}>⠿</span>
            </td>
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
