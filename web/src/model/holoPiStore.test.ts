import { describe, expect, test } from 'vitest';
import { medium } from '../test/FakeHoloPiApi';
import { holoPiReducer, initialState, selectGradable, selectGradeSources, selectShownId } from './holoPiStore';

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

  test('a medium renamed keeps its place and its space', () => {
    const state = holoPiReducer(listed, { type: 'mediumRenamed', medium: medium({ id: 'a', size: 100, name: 'new.mp4' }) });
    expect(state.media?.map(m => [m.id, m.name])).toEqual([['a', 'new.mp4'], ['b', 'helix_qs8x6a0.75.mp4']]);
    expect([state.size, state.free]).toEqual([150, 1000]);
  });

  test('a medium graded says so in the list and on the display, and the same again changes nothing', () => {
    const display = { ...initialDisplay(), source: 'media', media: medium({ id: 'b' }) } as const;
    const shown = holoPiReducer(listed, { type: 'displayRead', display });
    const state = holoPiReducer(shown, { type: 'mediumGraded', id: 'b', grade: 'on' });
    expect(state.media?.map(m => m.grade)).toEqual([null, 'on']);
    expect(state.display?.media?.grade).toBe('on');
    expect(holoPiReducer(state, { type: 'mediumGraded', id: 'b', grade: 'on' })).toBe(state);
    const other = holoPiReducer(state, { type: 'mediumGraded', id: 'a', grade: 'off' });
    expect([other.media?.[0].grade, other.display]).toEqual(['off', state.display]);
  });

  test('a grade can be copied from the other graded quilts, also one switched off', () => {
    const items = [medium({ id: 'a', grade: 'on' }), medium({ id: 'b', grade: 'off' }), medium({ id: 'c' }),
                   medium({ id: 'd', grade: 'on' })];
    const state = holoPiReducer(initialState, { type: 'mediaListed', list: { items, size: 0, free: 0 } });
    expect(selectGradeSources(state, 'a').map(m => m.id)).toEqual(['b', 'd']);
    expect(selectGradeSources(initialState, 'a')).toEqual([]);
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

  test('the quilt shown can be graded, through the GPU, and nothing else', () => {
    function shows(kind: 'quilt' | 'quilt video') {
      const display = { ...initialDisplay(), source: 'media', media: medium({ id: 'b', kind }) } as const;
      return holoPiReducer(listed, { type: 'displayRead', display });
    }
    expect(selectGradable(shows('quilt'))).toEqual({ id: 'b', why: null });
    expect(selectGradable(shows('quilt video')).id).toBeNull();
    expect(selectGradable(listed).id).toBeNull();
    const drm = { version: '0.1.0', screen: 'drm', looking_glass: null, calibration_error: null, display: shows('quilt').display! };
    expect(selectGradable(holoPiReducer(listed, { type: 'statusRead', status: drm })).why).toContain('GPU');
  });
});

function initialDisplay() {
  return { source: null, media: null, name: null, kind: null, reverse: false, shown: false, shown_on: null,
           error: null, frame_rate: null, decoder: null, warning: null };
}
