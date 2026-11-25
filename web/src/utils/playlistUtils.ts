// The playlist as the play tab shows it: every medium of the library, with how it plays, also those never in the
// playlist, at the defaults. Used by usePlaylist and the playlist's table.
import type { Medium, Playlist, PlaylistEntry } from '../services/HoloPiApi';

/** How long a quilt is shown, and how often a video plays, unless changed: the server's defaults. */
export const DEFAULT_SECONDS = 10;
export const DEFAULT_LOOPS = 1;
/** The limits the server takes. */
export const SECONDS_RANGE = { min: 1, max: 86400 };
export const LOOPS_RANGE = { min: 1, max: 1000 };

export type PlaylistRow = {
  medium: Medium;
  enabled: boolean;
  /** How long a quilt is shown; null for a video. */
  seconds: number | null;
  /** How often a video plays; null for a quilt. */
  loops: number | null;
  /** How long it plays in all, in seconds; null for a video whose length its file does not say. */
  time: number | null;
};

/** A row for each medium, in the library's order. */
export function makeRows(media: Medium[], playlist: Playlist): PlaylistRow[] {
  const entries = new Map(playlist.items.map(entry => [entry.media_id, entry]));
  return media.map(medium => {
    const entry = entries.get(medium.id);
    const enabled = entry?.enabled ?? false;
    if (medium.kind === 'quilt') {
      const seconds = entry?.seconds ?? DEFAULT_SECONDS;
      return { medium, enabled, seconds, loops: null, time: seconds };
    }
    const loops = entry?.loops ?? DEFAULT_LOOPS;
    return { medium, enabled, seconds: null, loops, time: medium.duration === null ? null : loops * medium.duration };
  });
}

/** The entries the server keeps of the rows: of the library's media only, so none that is gone. */
export function toEntries(rows: PlaylistRow[]): PlaylistEntry[] {
  return rows.map(({ medium, enabled, seconds, loops }) => ({ media_id: medium.id, enabled, seconds, loops }));
}

/** How long the rows enabled play together, in seconds, and whether that is all: not if a video's length is unknown. */
export function totalTime(rows: PlaylistRow[]): { seconds: number; exact: boolean } {
  const played = rows.filter(row => row.enabled);
  return { seconds: played.reduce((sum, row) => sum + (row.time ?? 0), 0), exact: played.every(row => row.time !== null) };
}
