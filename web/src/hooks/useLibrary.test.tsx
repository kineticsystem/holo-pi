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

test('playing a medium marks it shown, and removing it shows black', async () => {
  const result = setUp(new FakeHoloPiApi([medium({ id: 'a' }), medium({ id: 'b' })]));
  await waitFor(() => expect(result.current.library.media).not.toBeNull());
  await act(() => result.current.display.play('b'));
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

test('a medium that is gone cannot be played, and the page says why', async () => {
  const result = setUp(new FakeHoloPiApi());
  await act(() => result.current.display.play('gone'));
  expect(result.current.display.error).toBe("no quilt or video of the id 'gone'");
});
