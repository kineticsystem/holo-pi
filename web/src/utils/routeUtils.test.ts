import { expect, test } from 'vitest';
import { formatRoute, parseRoute } from './routeUtils';

test('the library is the page of no address, and of an unknown one', () => {
  for (const hash of ['', '#', '#/', '#/grade', '#/grade/', '#/other/3f9a1c2e', '#/grade/%']) {
    expect(parseRoute(hash)).toEqual({ page: 'library' });
  }
});

test('the grading page has its quilt in its address', () => {
  expect(parseRoute('#/grade/3f9a1c2e')).toEqual({ page: 'grade', id: '3f9a1c2e' });
});

test('an address is read back as it was written', () => {
  for (const route of [{ page: 'library' }, { page: 'grade', id: 'a b/c' }] as const) {
    expect(parseRoute(formatRoute(route))).toEqual(route);
  }
});
