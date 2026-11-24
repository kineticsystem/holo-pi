import { act, renderHook, waitFor } from '@testing-library/react';
import { expect, test } from 'vitest';
import { FakeHoloPiApi, medium } from '../test/FakeHoloPiApi';
import { makeWrapper } from '../test/renderWithServices';
import { useDisplay } from './useDisplay';
import { useGrade } from './useGrade';
import { useLibrary } from './useLibrary';

async function setUp(api = new FakeHoloPiApi([medium({ id: 'a', kind: 'quilt' })])) {
  const { result } = renderHook(() => ({ grade: useGrade('a'), display: useDisplay(), library: useLibrary() }), { wrapper: makeWrapper({ api }) });
  await waitFor(() => expect(result.current.grade.loading || result.current.library.loading).toBe(false));
  return { api, result };
}

function valueOf(result: { current: { grade: ReturnType<typeof useGrade> } }, id: string) {
  return result.current.grade.sections?.flatMap(s => s.tools).find(t => t.parameter.id === id)?.value;
}

test('the tools and the grade kept come from the server', async () => {
  const api = new FakeHoloPiApi([medium({ id: 'a', kind: 'quilt' })]);
  api.grades.set('a', { enabled: true, values: { exposure: 1.5 } });
  const { result } = await setUp(api);
  expect(result.current.grade.sections?.map(s => s.title)).toEqual(['Color', 'Light', 'Effects']);
  expect([valueOf(result, 'exposure'), valueOf(result, 'contrast'), result.current.grade.changed]).toEqual([1.5, 0, true]);
});

test('a change shows at once, and goes to the server with the values before it', async () => {
  const { api, result } = await setUp();
  act(() => result.current.grade.change('exposure', 1));
  await act(async () => result.current.grade.change('contrast', 20));
  expect(valueOf(result, 'contrast')).toBe(20);
  expect(api.grades.get('a')).toEqual({ enabled: true, values: { exposure: 1, contrast: 20 } });
});

test('while the screen draws, only the newest change waits', async () => {
  const { api, result } = await setUp();
  api.holdGrades = true;
  for (const value of [10, 20, 30]) act(() => result.current.grade.change('contrast', value));
  expect(api.gradesSet.map(g => g.values.contrast)).toEqual([10]);
  expect(valueOf(result, 'contrast')).toBe(30);
  await act(async () => api.finishGrade());
  await waitFor(() => expect(api.gradesSet.map(g => g.values.contrast)).toEqual([10, 30]));
  await act(async () => api.finishGrade());
  expect(api.grades.get('a')?.values.contrast).toBe(30);
});

test('the original is shown to compare, and the values are kept', async () => {
  const { api, result } = await setUp();
  await act(async () => result.current.grade.change('contrast', 20));
  await act(async () => result.current.grade.toggleOriginal());
  expect(result.current.grade.showsOriginal).toBe(true);
  expect(api.grades.get('a')).toEqual({ enabled: false, values: { contrast: 20 } });
  await act(async () => result.current.grade.change('contrast', 30));
  expect(result.current.grade.showsOriginal).toBe(false);
});

test('a reset puts every default back', async () => {
  const { api, result } = await setUp();
  await act(async () => result.current.grade.change('contrast', 20));
  await act(async () => result.current.grade.reset());
  expect([valueOf(result, 'contrast'), result.current.grade.changed]).toEqual([0, false]);
  expect(api.grades.get('a')).toEqual({ enabled: true, values: {} });
});

test('a change the server refuses says why', async () => {
  const { api, result } = await setUp();
  api.failWith = 'grading needs a screen drawn by the GPU';
  await act(async () => result.current.grade.change('contrast', 20));
  expect(result.current.grade.error).toBe('grading needs a screen drawn by the GPU');
  api.failWith = null;
  await act(async () => result.current.grade.change('contrast', 30));
  expect(result.current.grade.error).toBeNull();
});

test('the library and the display say whether the quilt is graded', async () => {
  const { api, result } = await setUp();
  await act(() => result.current.display.show('a'));
  const grades = () => [result.current.library.media?.[0].grade, result.current.display.display?.media?.grade];
  expect(grades()).toEqual([null, null]);
  await act(async () => result.current.grade.change('contrast', 20));
  expect(grades()).toEqual(['on', 'on']);
  await act(async () => result.current.grade.toggleOriginal());
  expect(grades()).toEqual(['off', 'off']);
  api.failWith = 'grading needs a screen drawn by the GPU';
  await act(async () => result.current.grade.reset());
  expect(grades()).toEqual(['off', 'off']); // The server still has it.
  api.failWith = null;
  await act(async () => result.current.grade.reset());
  expect(grades()).toEqual([null, null]);
});

test('it says whether the Looking Glass shows the quilt', async () => {
  const { result } = await setUp();
  expect(result.current.grade.onScreen).toBe(false);
  await act(() => result.current.display.show('a'));
  expect(result.current.grade.onScreen).toBe(true);
});

test('a save keeps the quilt with its grade as a new one, in the library', async () => {
  const { api, result } = await setUp();
  expect(result.current.grade.canSave).toBe(false); // Nothing to save yet.
  await act(async () => result.current.grade.change('contrast', 20));
  await act(() => result.current.grade.save());
  expect(api.saves).toEqual([{ id: 'a', grade: { enabled: true, values: { contrast: 20 } } }]);
  expect(result.current.grade.savedName).toBe('helix-graded_qs8x6a0.75.png');
  expect(result.current.library.media?.map(m => m.id)).toEqual(['a', 'saved-1']);
  await act(async () => result.current.grade.change('contrast', 30));
  expect(result.current.grade.savedName).toBeNull();
});

test('a save waits for the last change to reach the server', async () => {
  const { api, result } = await setUp();
  api.holdGrades = true;
  for (const value of [10, 20]) act(() => result.current.grade.change('contrast', value));
  act(() => void result.current.grade.save());
  await act(async () => api.finishGrade());
  expect(api.saves).toEqual([]);
  await act(async () => api.finishGrade());
  await waitFor(() => expect(api.saves.map(s => s.grade?.values.contrast)).toEqual([20]));
});

test('one save at a time', async () => {
  const { api, result } = await setUp();
  api.holdSaves = true;
  await act(async () => result.current.grade.change('contrast', 20));
  await act(async () => void result.current.grade.save());
  expect([result.current.grade.saving, result.current.grade.canSave]).toEqual([true, false]);
  await act(() => result.current.grade.save());
  expect(api.saves).toHaveLength(1);
  await act(async () => api.finishSave());
  await waitFor(() => expect(result.current.grade.saving).toBe(false));
});

test('the original shown is not saved, and a save that fails says why', async () => {
  const { api, result } = await setUp();
  await act(async () => result.current.grade.change('contrast', 20));
  await act(async () => result.current.grade.toggleOriginal());
  expect(result.current.grade.canSave).toBe(false);
  await act(async () => result.current.grade.toggleOriginal());
  api.failWith = 'the disk is full';
  await act(() => result.current.grade.save());
  expect([result.current.grade.error, result.current.grade.savedName]).toEqual(['the disk is full', null]);
});
