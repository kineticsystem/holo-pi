import { act, renderHook, waitFor } from '@testing-library/react';
import { expect, test } from 'vitest';
import { FakeHoloPiApi, medium } from '../test/FakeHoloPiApi';
import { makeWrapper } from '../test/renderWithServices';
import { usePlaylist } from './usePlaylist';

async function setUp(prepare: (api: FakeHoloPiApi) => void = () => {}) {
  const api = new FakeHoloPiApi([medium({ id: 'q', kind: 'quilt', duration: null }), medium({ id: 'v', duration: 20 })]);
  prepare(api);
  const { result } = renderHook(() => usePlaylist(), { wrapper: makeWrapper({ api }) });
  await waitFor(() => expect(result.current.loading).toBe(false));
  return { api, result };
}

test('nothing is played at first, and nothing can be', async () => {
  const { api, result } = await setUp();
  expect(result.current.rows?.map(row => row.enabled)).toEqual([false, false]);
  expect(result.current.canPlay).toBe(false);
  await act(() => result.current.play());
  expect(api.plays).toEqual([]);
});

test('a change shows at once, and the server keeps it', async () => {
  const { api, result } = await setUp();
  act(() => result.current.setEnabled('q', true));
  act(() => result.current.setSeconds('q', 4));
  act(() => result.current.setLoops('v', 3));
  await act(async () => result.current.setRepeat(false));
  expect([result.current.count, result.current.total.seconds, result.current.repeat]).toEqual([1, 4, false]);
  await waitFor(() => expect(api.playlist).toEqual({
    repeat: false, items: [{ media_id: 'q', enabled: true, seconds: 4, loops: null },
                           { media_id: 'v', enabled: false, seconds: null, loops: 3 }],
  }));
});

test('all are ticked in one go, and a medium left out keeps its settings', async () => {
  const { api, result } = await setUp();
  await act(async () => result.current.setLoops('v', 3));
  await act(async () => result.current.setAllEnabled(true));
  expect(result.current.count).toBe(2);
  await act(async () => result.current.setAllEnabled(false));
  expect(result.current.count).toBe(0);
  await waitFor(() => expect(api.playlist.items[1]).toEqual({ media_id: 'v', enabled: false, seconds: null, loops: 3 }));
});

test('play starts what the page shows, once the last change is kept', async () => {
  const { api, result } = await setUp(api => { api.holdPlaylists = true; });
  act(() => result.current.setAllEnabled(true));
  act(() => result.current.setSeconds('q', 7));
  let playing: Promise<void> = Promise.resolve();
  act(() => { playing = result.current.play(); });
  expect(api.plays).toEqual([]);
  expect(result.current.canPlay).toBe(false);
  act(() => api.finishPlaylist());
  await waitFor(() => expect(api.playlistsSet).toHaveLength(2));
  act(() => api.finishPlaylist());
  await act(() => playing);
  expect(api.plays[0].items.map(entry => [entry.enabled, entry.seconds])).toEqual([[true, 7], [true, null]]);
  expect([result.current.playing, result.current.playingId, result.current.canPlay]).toEqual([true, 'q', true]);
});

test('stop shows black', async () => {
  const { result } = await setUp();
  act(() => result.current.setAllEnabled(true));
  expect(result.current.canStop).toBe(false);
  await act(() => result.current.play());
  expect(result.current.canStop).toBe(true);
  await act(() => result.current.stop());
  expect([result.current.playing, result.current.playingId]).toEqual([false, null]);
});

test('a change the server refuses is undone, says why, and does not play; then play works again', async () => {
  const { api, result } = await setUp(api => {
    api.playlist = { repeat: true, items: [{ media_id: 'q', enabled: true, seconds: 5, loops: null }] };
    api.refusePlaylist = "no medium of the id 'v'";
  });
  act(() => result.current.setSeconds('q', 9));
  await act(() => result.current.play());
  expect(api.plays).toEqual([]);
  expect(result.current.error).toBe("no medium of the id 'v'");
  expect(result.current.rows?.[0].seconds).toBe(5);
  await act(() => result.current.play());
  expect(api.plays).toHaveLength(1);
});

test('an unreachable server says so', async () => {
  const { result } = await setUp(api => { api.failWith = 'cannot reach the server'; });
  expect([result.current.error, result.current.rows]).toEqual(['cannot reach the server', null]);
});
