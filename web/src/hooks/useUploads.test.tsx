import { act, renderHook, waitFor } from '@testing-library/react';
import { expect, test } from 'vitest';
import { useHoloPiStore } from '../model/HoloPiStoreContext';
import { FakeHoloPiApi } from '../test/FakeHoloPiApi';
import { makeWrapper } from '../test/renderWithServices';
import { useUploads } from './useUploads';

const options = { columns: null, rows: null };
const file = (name: string) => new File(['quilt'], name);

function setUp(api = new FakeHoloPiApi()) {
  const { result } = renderHook(() => ({ uploads: useUploads(), store: useHoloPiStore() }),
                                { wrapper: makeWrapper({ api }) });
  return { api, result };
}

const statuses = (jobs: { file: File; status: string }[]) => jobs.map(job => [job.file.name, job.status]);

test('several files go in one after another, each into the list', async () => {
  const api = new FakeHoloPiApi();
  api.holdUploads = true;
  const { result } = setUp(api);
  act(() => result.current.uploads.add([file('a.mp4'), file('b.mp4')], options));
  await waitFor(() => expect(statuses(result.current.uploads.jobs)).toEqual([['a.mp4', 'sending'], ['b.mp4', 'waiting']]));
  expect(api.uploads.map(upload => upload.file.name)).toEqual(['a.mp4']); // One at a time.
  await act(async () => api.finishUpload());
  await waitFor(() => expect(statuses(result.current.uploads.jobs)).toEqual([['a.mp4', 'done'], ['b.mp4', 'sending']]));
  await act(async () => api.finishUpload());
  await waitFor(() => expect(result.current.uploads.busy).toBe(false));
  expect(result.current.store.state.media?.map(m => m.name)).toEqual(['a.mp4', 'b.mp4']);
});

test('a single file is shown at once', async () => {
  const { api, result } = setUp();
  act(() => result.current.uploads.add([file('a.mp4')], options));
  await waitFor(() => expect(result.current.uploads.busy).toBe(false));
  expect(api.uploads.map(upload => upload.options.play)).toEqual([true]);
  expect(result.current.store.state.display?.name).toBe('a.mp4');
});

test('of several, only the first is shown, the others only kept, all with their views in order', async () => {
  const { api, result } = setUp();
  act(() => result.current.uploads.add([file('a.mp4'), file('b.mp4'), file('c.mp4')], options));
  await waitFor(() => expect(result.current.uploads.busy).toBe(false));
  expect(api.uploads.map(upload => upload.options.play)).toEqual([true, false, false]);
  expect(api.uploads.every(upload => !upload.options.reverse)).toBe(true);
  expect(result.current.store.state.display?.name).toBe('a.mp4');
});

test('a file that fails says why, and the next goes in', async () => {
  const api = new FakeHoloPiApi();
  api.failing.add('bad.png');
  const { result } = setUp(api);
  act(() => result.current.uploads.add([file('bad.png'), file('good.mp4')], options));
  await waitFor(() => expect(result.current.uploads.busy).toBe(false));
  expect(statuses(result.current.uploads.jobs)).toEqual([['bad.png', 'failed'], ['good.mp4', 'done']]);
  expect(result.current.uploads.jobs[0].error).toBe('cannot read bad.png');
});

test('a file waiting can be stopped before it is sent, and the one sending too', async () => {
  const api = new FakeHoloPiApi();
  api.holdUploads = true;
  const { result } = setUp(api);
  act(() => result.current.uploads.add([file('a.mp4'), file('b.mp4'), file('c.mp4')], options));
  await waitFor(() => expect(result.current.uploads.jobs[0].status).toBe('sending'));
  act(() => result.current.uploads.cancel(result.current.uploads.jobs[1].id));
  act(() => result.current.uploads.cancel(result.current.uploads.jobs[0].id));
  await waitFor(() => expect(result.current.uploads.jobs[2].status).toBe('sending'));
  expect(statuses(result.current.uploads.jobs)).toEqual([['a.mp4', 'stopped'], ['b.mp4', 'stopped'], ['c.mp4', 'sending']]);
  expect(api.uploads.map(upload => upload.file.name)).toEqual(['a.mp4', 'c.mp4']);
});

test('stop all, then clear the finished', async () => {
  const api = new FakeHoloPiApi();
  api.holdUploads = true;
  const { result } = setUp(api);
  act(() => result.current.uploads.add([file('a.mp4'), file('b.mp4')], options));
  await waitFor(() => expect(result.current.uploads.jobs[0].status).toBe('sending'));
  act(() => result.current.uploads.cancelAll());
  await waitFor(() => expect(result.current.uploads.busy).toBe(false));
  act(() => result.current.uploads.clearFinished());
  expect(result.current.uploads.jobs).toEqual([]);
});

test('a layout needs both columns and rows', () => {
  const { api, result } = setUp();
  act(() => result.current.uploads.add([file('a.png')], { ...options, columns: 8 }));
  expect(result.current.uploads.error).toBe('Give both columns and rows, or neither.');
  expect(api.uploads).toEqual([]);
});
