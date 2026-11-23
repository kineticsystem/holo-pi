import { expect, test } from 'vitest';
import { moveNextTo, sameOrder, stepThrough } from './listUtils';

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

test('an id moves just before or just after another', () => {
  expect(moveNextTo(['a', 'b', 'c', 'd'], 'd', 'b', false)).toEqual(['a', 'd', 'b', 'c']);
  expect(moveNextTo(['a', 'b', 'c', 'd'], 'a', 'c', true)).toEqual(['b', 'c', 'a', 'd']);
  expect(moveNextTo(['a', 'b', 'c'], 'a', 'c', true)).toEqual(['b', 'c', 'a']);
  expect(moveNextTo(['a', 'b', 'c'], 'c', 'a', false)).toEqual(['c', 'a', 'b']);
});

test('a move onto itself, or of an id not there, keeps the order', () => {
  expect(moveNextTo(['a', 'b'], 'a', 'a', true)).toEqual(['a', 'b']);
  expect(moveNextTo(['a', 'b'], 'gone', 'a', false)).toEqual(['a', 'b']);
  expect(moveNextTo(['a', 'b'], 'a', 'b', false)).toEqual(['a', 'b']);
});

test('two lists are in the same order only with the same ids in the same places', () => {
  expect(sameOrder(['a', 'b'], ['a', 'b'])).toBe(true);
  expect(sameOrder(['a', 'b'], ['b', 'a'])).toBe(false);
  expect(sameOrder(['a'], ['a', 'b'])).toBe(false);
});
