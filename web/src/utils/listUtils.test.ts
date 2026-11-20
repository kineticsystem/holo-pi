import { expect, test } from 'vitest';
import { stepThrough } from './listUtils';

test('a step goes to the next or the previous id', () => {
  expect(stepThrough(['a', 'b', 'c'], 'b', 1)).toBe('c');
  expect(stepThrough(['a', 'b', 'c'], 'b', -1)).toBe('a');
});

test('a step stops at the ends', () => {
  expect(stepThrough(['a', 'b', 'c'], 'c', 1)).toBe('c');
  expect(stepThrough(['a', 'b', 'c'], 'a', -1)).toBe('a');
});

test('from nothing, or an id gone, down starts at the first and up at the last', () => {
  expect(stepThrough(['a', 'b', 'c'], null, 1)).toBe('a');
  expect(stepThrough(['a', 'b', 'c'], 'gone', -1)).toBe('c');
});

test('an empty list has nowhere to go', () => {
  expect(stepThrough([], null, 1)).toBeNull();
});
