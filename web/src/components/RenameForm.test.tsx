import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test, vi } from 'vitest';
import { RenameForm } from './RenameForm';

function setUp(taken = true) {
  const onRename = vi.fn((_name: string) => Promise.resolve(taken));
  const onDone = vi.fn();
  const onTableKey = vi.fn();
  render(<div onKeyDown={onTableKey}><RenameForm name="helix_qs8x6a0.75.mp4" onRename={onRename} onDone={onDone} /></div>);
  return { onRename, onDone, onTableKey, input: screen.getByRole('textbox') as HTMLInputElement };
}

test('it starts with the title selected, so that typing keeps the layout and the extension', async () => {
  const { onRename, onDone, input } = setUp();
  expect(input).toHaveFocus();
  expect([input.selectionStart, input.selectionEnd]).toEqual([0, 5]);
  await userEvent.keyboard('spiral{Enter}');
  expect(onRename).toHaveBeenCalledWith('spiral_qs8x6a0.75.mp4');
  expect(onDone).toHaveBeenCalled();
});

test('a name refused stays to be corrected', async () => {
  const { onDone, input } = setUp(false);
  await userEvent.keyboard('spiral{Enter}');
  expect(onDone).not.toHaveBeenCalled();
  expect(input.value).toBe('spiral_qs8x6a0.75.mp4');
});

test('Escape and Cancel leave the name as it was', async () => {
  const { onRename, onDone } = setUp();
  await userEvent.keyboard('spiral{Escape}');
  await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
  expect(onDone).toHaveBeenCalledTimes(2);
  expect(onRename).not.toHaveBeenCalled();
});

test('the same name asks nothing, and no name cannot be saved', async () => {
  const { onRename, onDone, input } = setUp();
  await userEvent.keyboard('{Enter}');
  expect(onDone).toHaveBeenCalled();
  await userEvent.clear(input);
  expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
  expect(onRename).not.toHaveBeenCalled();
});

test('the arrow keys stay in the text', () => {
  const { onTableKey, input } = setUp();
  fireEvent.keyDown(input, { key: 'ArrowDown' });
  expect(onTableKey).not.toHaveBeenCalled();
});
