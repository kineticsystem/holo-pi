import { expect, test } from 'vitest';
import { formatBytes, formatDuration, formatLayout, formatTimeSpan } from './formatUtils';

test('sizes are written in decimal units', () => {
  expect(formatBytes(512)).toBe('512 B');
  expect(formatBytes(122438702)).toBe('122.4 MB');
  expect(formatBytes(200e9)).toBe('200.0 GB');
});

test('lengths are minutes and seconds, or nothing when unknown', () => {
  expect(formatDuration(20)).toBe('0:20');
  expect(formatDuration(95.4)).toBe('1:35');
  expect(formatDuration(null)).toBe('');
});

test('lengths of time are written with their units', () => {
  expect([0, 20, 60, 80, 3600, 3700].map(formatTimeSpan)).toEqual(['0 s', '20 s', '1 min', '1 min 20 s', '1 h', '1 h 1 min']);
});

test('a video without a layout is a hologram', () => {
  expect(formatLayout(8, 6)).toBe('8 × 6');
  expect(formatLayout(null, null)).toBe('hologram');
});
