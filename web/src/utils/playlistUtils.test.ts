import { expect, test } from 'vitest';
import { medium } from '../test/FakeHoloPiApi';
import { makeRows, toEntries, totalTime } from './playlistUtils';

const media = [medium({ id: 'q', kind: 'quilt', duration: null }), medium({ id: 'v', duration: 20 }),
               medium({ id: 'h', kind: 'hologram video', duration: null })];

test('every medium has a row, in the library\'s order, not played and at the defaults at first', () => {
  const rows = makeRows(media, []);
  expect(rows.map(row => [row.medium.id, row.enabled, row.seconds, row.loops, row.time])).toEqual([
    ['q', false, 10, null, 10], ['v', false, null, 1, 20], ['h', false, null, 1, null],
  ]);
});

test('the playlist says how each plays, and one no longer in the library is left out', () => {
  const items = [{ media_id: 'gone', enabled: true, seconds: 5, loops: null },
                 { media_id: 'v', enabled: true, seconds: null, loops: 3 },
                 { media_id: 'q', enabled: false, seconds: 5, loops: null }];
  const rows = makeRows(media, items);
  expect(rows.map(row => [row.enabled, row.seconds, row.loops])).toEqual([[false, 5, null], [true, null, 3], [false, null, 1]]);
  expect(toEntries(rows).map(entry => entry.media_id)).toEqual(['q', 'v', 'h']);
});

test('the time is that of the media played, and exact only when every length is known', () => {
  const entry = { enabled: true, seconds: null, loops: null };
  const two = makeRows(media, [{ ...entry, media_id: 'q' }, { ...entry, media_id: 'v', loops: 2 }]);
  expect(totalTime(two)).toEqual({ seconds: 50, exact: true });
  const unknown = makeRows(media, [{ ...entry, media_id: 'q' }, { ...entry, media_id: 'h' }]);
  expect(totalTime(unknown)).toEqual({ seconds: 10, exact: false });
});
