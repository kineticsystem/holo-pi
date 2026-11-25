// The play tab's view model: the playlist, a row for each medium of the library, and the commands to change it, play it
// and stop it. A change shows at once and goes to the server, which keeps it; while one is on its way, only the newest
// waits. Play starts what the page shows: it waits for the last change to be kept.
import { useCallback, useEffect, useRef, useState } from 'react';
import { selectNoTransitions, selectPlaying, selectShownId } from '../model/holoPiStore';
import { useHoloPiStore } from '../model/HoloPiStoreContext';
import type { Playlist, Transition } from '../services/HoloPiApi';
import { useServices } from '../services/ServicesContext';
import { makeLatest } from '../utils/latestUtils';
import { makeRows, toEntries, totalTime, type PlaylistRow } from '../utils/playlistUtils';
import { useDisplay } from './useDisplay';

export function usePlaylist() {
  const { state, dispatch } = useHoloPiStore();
  const { api } = useServices();
  const display = useDisplay();
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const keptRef = useRef(true); // Whether the server took the changes that play() waits for.

  const read = useCallback(async (signal?: AbortSignal) => {
    const [media, playlist] = await Promise.all([api.listMedia(signal), api.getPlaylist(signal)]);
    if (signal?.aborted) return;
    if (media.ok) dispatch({ type: 'mediaListed', list: media.value });
    if (playlist.ok) dispatch({ type: 'playlistRead', playlist: playlist.value });
    const failed = [media, playlist].find(result => !result.ok);
    if (failed && !failed.ok) setError(failed.error);
  }, [api, dispatch]);

  const [latest] = useState(() => makeLatest<Playlist>(async next => {
    const result = await api.setPlaylist(next);
    if (!result.ok) keptRef.current = false;
    setError(result.ok ? null : result.error);
    if (!result.ok) await read(); // E.g. a medium is gone: the page goes back to what the server has.
  }));

  // The playlist and the library, from the server, when the tab opens.
  useEffect(() => {
    const controller = new AbortController();
    void read(controller.signal);
    return () => controller.abort();
  }, [read]);

  const { media, playlist } = state;
  const rows = media && playlist ? makeRows(media, playlist.items) : null;
  const playing = selectPlaying(state);
  const count = rows?.filter(row => row.enabled).length ?? 0;
  const canPlay = count > 0 && !display.pending && !starting;

  function apply(next: PlaylistRow[], fields: Partial<Omit<Playlist, 'items'>> = {}) {
    if (!playlist) return;
    const changed = { ...playlist, ...fields, items: toEntries(next) };
    dispatch({ type: 'playlistRead', playlist: changed });
    latest.send(changed);
  }

  function change(id: string, fields: Partial<Pick<PlaylistRow, 'enabled' | 'seconds' | 'loops'>>) {
    if (rows) apply(rows.map(row => (row.medium.id === id ? { ...row, ...fields } : row)));
  }

  async function play() {
    if (!canPlay) return;
    setStarting(true);
    keptRef.current = true; // A change refused before was undone on the page.
    await latest.settled();
    if (keptRef.current) await display.showPlaylist();
    setStarting(false);
  }

  return {
    rows,
    repeat: playlist?.repeat ?? true,
    transition: playlist?.transition ?? 'cut',
    transitionSeconds: playlist?.transition_seconds ?? 1,
    /** Why there are no transitions, if so. */
    noTransitions: selectNoTransitions(state),
    /** How many media play, and how long they take, one time through. */
    count,
    total: totalTime(rows ?? []),
    playing,
    /** The medium the playlist is at, while it plays. */
    playingId: playing ? selectShownId(state) : null,
    canPlay,
    canStop: playing && !display.pending,
    loading: rows === null && error === null,
    error: error ?? display.error,
    setEnabled: (id: string, enabled: boolean) => change(id, { enabled }),
    setAllEnabled(enabled: boolean) {
      if (rows) apply(rows.map(row => ({ ...row, enabled })));
    },
    setSeconds: (id: string, seconds: number) => change(id, { seconds }),
    setLoops: (id: string, loops: number) => change(id, { loops }),
    setRepeat(repeat: boolean) {
      if (rows) apply(rows, { repeat });
    },
    setTransition(transition: Transition) {
      if (rows) apply(rows, { transition });
    },
    setTransitionSeconds(seconds: number) {
      if (rows) apply(rows, { transition_seconds: seconds });
    },
    play,
    stop: () => display.showBlack(),
  };
}
