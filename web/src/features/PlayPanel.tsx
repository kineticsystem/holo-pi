// The play tab: which media of the library play one after the other, for how long each, and the buttons to play them.
import { ErrorMessage } from '../components/ErrorMessage';
import { TransitionSelect } from '../components/TransitionSelect';
import { PlaylistTable } from '../components/PlaylistTable';
import { usePlaylist } from '../hooks/usePlaylist';
import { formatTimeSpan } from '../utils/formatUtils';

export function PlayPanel() {
  const playlist = usePlaylist();
  const { seconds, exact } = playlist.total;
  return (
    <section aria-label="Play">
      <p className="totals">
        <button className="primary" disabled={!playlist.canPlay} onClick={() => void playlist.play()}>
          {playlist.playing ? '▶ Play from the start' : '▶ Play'}
        </button>
        <button disabled={!playlist.canStop} title="Shows black" onClick={() => void playlist.stop()}>■ Stop</button>
        <label>
          <input type="checkbox" checked={playlist.repeat} disabled={playlist.rows === null}
                 onChange={event => playlist.setRepeat(event.target.checked)} /> Repeat
        </label>
        <TransitionSelect transition={playlist.transition} seconds={playlist.transitionSeconds}
                          disabled={playlist.rows === null} why={playlist.noTransitions}
                          onTransition={playlist.setTransition} onSeconds={playlist.setTransitionSeconds} />
        <span>
          {playlist.count === 0 ? 'Tick what to play'
            : `${playlist.count} media, ${exact ? '' : 'more than '}${formatTimeSpan(seconds)}`}
        </span>
      </p>
      {playlist.loading && <p className="empty">Asking the server…</p>}
      {playlist.rows && (
        <PlaylistTable rows={playlist.rows} playingId={playlist.playingId} onEnable={playlist.setEnabled}
                       onEnableAll={playlist.setAllEnabled} onSeconds={playlist.setSeconds}
                       onLoops={playlist.setLoops} />
      )}
      <ErrorMessage text={playlist.error} />
    </section>
  );
}
