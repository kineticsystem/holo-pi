import { expect, test } from 'vitest';
import { splitName } from './nameUtils';

test.each([
  ['helix_qs8x6a0.75.mp4', 'helix', '_qs8x6a0.75.mp4'],
  ['my helix-graded_qs8x6a0.75.png', 'my helix-graded', '_qs8x6a0.75.png'],
  ['Anna.jpg__lkgrec.mp4', 'Anna.jpg__lkgrec', '.mp4'],
  ['plain.jpg', 'plain', '.jpg'],
  ['noextension', 'noextension', ''],
  ['_qs8x6a0.75.png', '_qs8x6a0.75.png', ''],
])('%s is %s and %s', (name, title, rest) => {
  expect(splitName(name)).toEqual({ title, rest });
});
