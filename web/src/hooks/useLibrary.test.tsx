import { act, renderHook, waitFor } from '@testing-library/react';
import { expect, test } from 'vitest';
import { FakeHoloPiApi, medium } from '../test/FakeHoloPiApi';
import { makeWrapper } from '../test/renderWithServices';
import { useDisplay } from './useDisplay';
import { useLibrary } from './useLibrary';

function setUp(api: FakeHoloPiApi) {
  return renderHook(() => ({ library: useLibrary(), display: useDisplay() }), { wrapper: makeWrapper({ api }) }).result;
}

test('the list comes from the server when the page opens', async () => {
  const result = setUp(new FakeHoloPiApi([medium({ id: 'a' }), medium({ id: 'b' })]));
  expect(result.current.library.loading).toBe(true);
  await waitFor(() => expect(result.current.library.media?.map(m => m.id)).toEqual(['a', 'b']));
  expect(result.current.library.free).toBe(9000);
});

test('showing a medium marks it shown, and removing it shows black', async () => {
  const result = setUp(new FakeHoloPiApi([medium({ id: 'a' }), medium({ id: 'b' })]));
  await waitFor(() => expect(result.current.library.media).not.toBeNull());
  await act(() => result.current.display.show('b'));
  expect(result.current.library.shownId).toBe('b');
  await act(() => result.current.library.remove('b'));
  expect(result.current.library.media?.map(m => m.id)).toEqual(['a']);
  expect(result.current.library.shownId).toBeNull();
});

test('an unreachable server says so', async () => {
  const api = new FakeHoloPiApi();
  api.failWith = 'cannot reach the server';
  const result = setUp(api);
  await waitFor(() => expect(result.current.library.error).toBe('cannot reach the server'));
  expect(result.current.library.loading).toBe(false);
});

test('a medium that is gone cannot be shown, and the page says why', async () => {
  const result = setUp(new FakeHoloPiApi());
  await act(() => result.current.display.show('gone'));
  expect(result.current.display.error).toBe("no quilt or video of the id 'gone'");
});

test('removing several takes them all from the list, the one shown too', async () => {
  const result = setUp(new FakeHoloPiApi([medium({ id: 'a' }), medium({ id: 'b' }), medium({ id: 'c' })]));
  await waitFor(() => expect(result.current.library.media).not.toBeNull());
  await act(() => result.current.display.show('c'));
  await act(() => result.current.library.removeMany(['a', 'c']));
  expect(result.current.library.media?.map(m => m.id)).toEqual(['b']);
  expect(result.current.library.shownId).toBeNull();
  expect(result.current.library.error).toBeNull();
});

test('a removal refused keeps that medium, removes the others, and says why', async () => {
  const api = new FakeHoloPiApi([medium({ id: 'a' }), medium({ id: 'b' }), medium({ id: 'c' })]);
  api.refusing.add('b');
  const result = setUp(api);
  await waitFor(() => expect(result.current.library.media).not.toBeNull());
  await act(() => result.current.library.removeMany(['a', 'b', 'c']));
  expect(result.current.library.media?.map(m => m.id)).toEqual(['b']);
  expect(result.current.library.error).toBe('1 of 3 not removed: cannot remove b');
});

test('media asked for while the screen changes: only the last one follows, and the arrows go on from it', async () => {
  const api = new FakeHoloPiApi([medium({ id: 'a' }), medium({ id: 'b' }), medium({ id: 'c' })]);
  const result = setUp(api);
  await waitFor(() => expect(result.current.library.media).not.toBeNull());
  api.holdShows = true;
  let first: Promise<void> = Promise.resolve();
  act(() => { first = result.current.display.show('a'); });
  act(() => { void result.current.display.show('b'); });
  act(() => { void result.current.display.show('c'); });
  expect(result.current.display.wanted).toBe('c');
  expect(result.current.display.pending).toBe(true);
  api.finishShow();
  await waitFor(() => expect(api.shows).toEqual(['a', 'c']));
  api.finishShow();
  await act(() => first);
  expect(result.current.library.shownId).toBe('c');
  expect(result.current.display.wanted).toBeNull();
  expect(result.current.display.pending).toBe(false);
});
