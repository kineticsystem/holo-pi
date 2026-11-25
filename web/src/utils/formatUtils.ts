// How the page writes sizes, lengths and dates, for the library and the display.

const UNITS = ['B', 'KB', 'MB', 'GB', 'TB'];

/** A size in bytes as the user reads it, e.g. 122438702 as "122.4 MB". */
export function formatBytes(bytes: number): string {
  let value = bytes;
  let unit = 0;
  while (value >= 1000 && unit < UNITS.length - 1) {
    value /= 1000;
    unit += 1;
  }
  return unit === 0 ? `${value} B` : `${value.toFixed(1)} ${UNITS[unit]}`;
}

/** A length in seconds, e.g. 20 as "0:20", or nothing when unknown. */
export function formatDuration(seconds: number | null): string {
  if (seconds === null) return '';
  const whole = Math.round(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`;
}

/** A length of time, e.g. 20 seconds as "20 s", 80 as "1 min 20 s", 3700 as "1 h 1 min". */
export function formatTimeSpan(seconds: number): string {
  const whole = Math.round(seconds);
  const [hours, minutes, rest] = [Math.floor(whole / 3600), Math.floor(whole / 60) % 60, whole % 60];
  if (hours > 0) return minutes ? `${hours} h ${minutes} min` : `${hours} h`;
  if (minutes > 0) return rest ? `${minutes} min ${rest} s` : `${minutes} min`;
  return `${rest} s`;
}

/** A medium's layout, e.g. "8 × 6", or "hologram" for a video interleaved already. */
export function formatLayout(columns: number | null, rows: number | null): string {
  return columns === null || rows === null ? 'hologram' : `${columns} × ${rows}`;
}

/** An ISO 8601 time in the user's own time zone, e.g. "17 Nov, 11:45". */
export function formatTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}
