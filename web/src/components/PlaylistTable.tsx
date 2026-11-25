// The playlist's media, one row each: a box to tick those played, and for how long, seconds for a quilt, times for a
// video. The row playing is marked.
import { formatDuration, formatTimeSpan } from '../utils/formatUtils';
import { LOOPS_RANGE, SECONDS_RANGE, type PlaylistRow } from '../utils/playlistUtils';
import { NumberField } from './NumberField';

type PlaylistTableProps = {
  rows: PlaylistRow[];
  playingId: string | null;
  onEnable: (id: string, on: boolean) => void;
  onEnableAll: (on: boolean) => void;
  onSeconds: (id: string, seconds: number) => void;
  onLoops: (id: string, loops: number) => void;
};

export function PlaylistTable({ rows, playingId, onEnable, onEnableAll, onSeconds, onLoops }: PlaylistTableProps) {
  if (rows.length === 0) return <p className="empty">The library is empty: upload a quilt or a video.</p>;
  const count = rows.filter(row => row.enabled).length;
  return (
    <table className="media playlist" aria-label="Playlist">
      <thead>
        <tr>
          <th className="select">
            <input type="checkbox" aria-label="Play all" checked={count === rows.length}
                   ref={box => { if (box) box.indeterminate = count > 0 && count < rows.length; }}
                   onChange={event => onEnableAll(event.target.checked)} />
          </th>
          <th>Name</th><th>Kind</th><th>Length</th><th>Play for</th><th>Time</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(({ medium, enabled, seconds, loops, time }) => (
          <tr key={medium.id} aria-current={medium.id === playingId ? 'true' : undefined}
              className={[medium.id === playingId && 'shown', !enabled && 'left-out'].filter(Boolean).join(' ')}>
            <td className="select">
              <input type="checkbox" aria-label={`Play ${medium.name}`} checked={enabled}
                     onChange={event => onEnable(medium.id, event.target.checked)} />
            </td>
            <td><span className="name">{medium.name}</span></td>
            <td>{medium.kind}</td>
            <td>{formatDuration(medium.duration)}</td>
            <td>
              {seconds !== null && (
                <NumberField label={`Seconds for ${medium.name}`} unit="seconds" value={seconds} {...SECONDS_RANGE}
                             disabled={!enabled} onChange={value => onSeconds(medium.id, value)} />
              )}
              {loops !== null && (
                <NumberField label={`Times for ${medium.name}`} unit={loops === 1 ? 'time' : 'times'} value={loops}
                             whole {...LOOPS_RANGE} disabled={!enabled} onChange={value => onLoops(medium.id, value)} />
              )}
            </td>
            <td>{enabled && time !== null ? formatTimeSpan(time) : ''}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
