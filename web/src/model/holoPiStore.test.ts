import { describe, expect, test } from 'vitest';
import { medium } from '../test/FakeHoloPiApi';
import { holoPiReducer, initialState, selectShownId } from './holoPiStore';

const listed = holoPiReducer(initialState, {
  type: 'mediaListed', list: { items: [medium({ id: 'a', size: 100 }), medium({ id: 'b', size: 50 })], size: 150, free: 1000 },
});

describe('the store', () => {
  test('an upload of a new name is added at the end, and takes its space', () => {
    const state = holoPiReducer(listed, { type: 'mediumUploaded', medium: medium({ id: 'c', size: 30 }) });
    expect(state.media?.map(m => m.id)).toEqual(['a', 'b', 'c']);
    expect([state.size, state.free]).toEqual([180, 970]);
  });

  test('an upload of a name the library has replaces it in place', () => {
    const state = holoPiReducer(listed, { type: 'mediumUploaded', medium: medium({ id: 'a', size: 120, name: 'new' }) });
    expect(state.media?.map(m => [m.id, m.name])).toEqual([['a', 'new'], ['b', 'helix_qs8x6a0.75.mp4']]);
    expect([state.size, state.free]).toEqual([170, 980]);
  });

  test('an order puts the media in it, and those it does not name after them', () => {
    const three = holoPiReducer(listed, { type: 'mediumUploaded', medium: medium({ id: 'c' }) });
    const state = holoPiReducer(three, { type: 'mediaOrdered', ids: ['b', 'a'] });
    expect(state.media?.map(m => m.id)).toEqual(['b', 'a', 'c']);
    expect([state.size, state.free]).toEqual([three.size, three.free]);
  });

  test('a removal gives its space back', () => {
    const state = holoPiReducer(listed, { type: 'mediumRemoved', id: 'a' });
    expect(state.media?.map(m => m.id)).toEqual(['b']);
    expect([state.size, state.free]).toEqual([50, 1100]);
  });

  test('removing them all empties the list', () => {
    const state = holoPiReducer(listed, { type: 'allMediaRemoved' });
    expect([state.media, state.size, state.free]).toEqual([[], 0, 1150]);
  });

  test('the medium shown comes from the display, not from a copy', () => {
    expect(selectShownId(listed)).toBeNull();
    const display = { source: 'media', media: medium({ id: 'b' }) } as const;
    const state = holoPiReducer(listed, { type: 'displayRead', display: { ...initialDisplay(), ...display } });
    expect(selectShownId(state)).toBe('b');
    const pattern = holoPiReducer(state, { type: 'displayRead', display: { ...initialDisplay(), source: 'test pattern' } });
    expect(selectShownId(pattern)).toBeNull();
  });
});

function initialDisplay() {
  return { source: null, media: null, name: null, kind: null, reverse: false, shown: false, shown_on: null,
           error: null, frame_rate: null, decoder: null, warning: null };
}
