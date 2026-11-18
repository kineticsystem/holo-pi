import { act, renderHook } from '@testing-library/react';
import { expect, test } from 'vitest';
import { useSelection } from './useSelection';

test('ticks and unticks, in the order of the list', () => {
  const { result } = renderHook(() => useSelection(['a', 'b', 'c']));
  act(() => result.current.toggle('c', true));
  act(() => result.current.toggle('a', true));
  expect(result.current.selected).toEqual(['a', 'c']);
  act(() => result.current.toggle('c', false));
  expect(result.current.selected).toEqual(['a']);
});

test('selects all, and none', () => {
  const { result } = renderHook(() => useSelection(['a', 'b']));
  act(() => result.current.selectAll(true));
  expect(result.current.selected).toEqual(['a', 'b']);
  act(() => result.current.selectAll(false));
  expect(result.current.selected).toEqual([]);
});

test('a medium gone from the list is no longer selected', () => {
  const { result, rerender } = renderHook(({ ids }) => useSelection(ids), { initialProps: { ids: ['a', 'b'] } });
  act(() => result.current.selectAll(true));
  rerender({ ids: ['b'] });
  expect(result.current.selected).toEqual(['b']);
});
