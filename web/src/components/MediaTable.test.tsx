import { createEvent, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test, vi } from 'vitest';
import { medium } from '../test/FakeHoloPiApi';
import { MediaTable } from './MediaTable';

function setUp(shownId: string | null = null, selected: string[] = [], currentId: string | null = shownId) {
  const onShow = vi.fn();
  const onMove = vi.fn();
  const onRename = vi.fn((_id: string, _name: string) => Promise.resolve(true));
  const onRemove = vi.fn();
  const onSelect = vi.fn();
  const onSelectAll = vi.fn();
  render(<MediaTable media={[medium({ id: 'a', name: 'helix_qs8x6a0.75.mp4' }), medium({ id: 'b', name: 'old.mp4', codec: 'h264', warning: 'not H.265' }),
                             medium({ id: 'c', name: 'knot_qs8x6a0.75.jpg', kind: 'quilt' })]}
                     shownId={shownId} currentId={currentId} selected={selected} disabled={false} contentUrl={id => `/api/media/${id}/content`}
                     onShow={onShow} onMove={onMove} onRename={onRename} onRemove={onRemove} onSelect={onSelect} onSelectAll={onSelectAll} />);
  return { onShow, onMove, onRename, onRemove, onSelect, onSelectAll };
}

test('a click on a row shows its medium, and there is no play button', async () => {
  const { onShow } = setUp();
  await userEvent.click(screen.getByText('old.mp4'));
  expect(onShow).toHaveBeenCalledWith('b');
  expect(screen.queryByRole('button', { name: 'Play' })).toBeNull();
});

test("a row's own controls do not show it", async () => {
  const { onShow } = setUp();
  await userEvent.click(screen.getByRole('checkbox', { name: 'Select old.mp4' }));
  await userEvent.click(screen.getAllByRole('button', { name: 'Remove' })[1]);
  expect(onShow).not.toHaveBeenCalled();
});

test('the arrow keys show the medium below or above the current one, and stop at the ends', async () => {
  const { onShow } = setUp('a');
  screen.getByRole('table').focus();
  await userEvent.keyboard('{ArrowDown}');
  expect(onShow).toHaveBeenLastCalledWith('b');
  await userEvent.keyboard('{ArrowUp}');
  expect(onShow).toHaveBeenCalledTimes(1);  // Up from the first row: nowhere to go.
});

test('with nothing shown, the down arrow starts at the first row', async () => {
  const { onShow } = setUp();
  screen.getByRole('table').focus();
  await userEvent.keyboard('{ArrowDown}');
  expect(onShow).toHaveBeenCalledWith('a');
});

test('the arrows go on from the medium asked for, ahead of the one on the screen', async () => {
  const { onShow } = setUp('a', [], 'b');
  expect(screen.getByText('old.mp4').closest('tr')).toHaveAttribute('aria-current', 'true');
  screen.getByRole('table').focus();
  await userEvent.keyboard('{ArrowUp}');
  expect(onShow).toHaveBeenCalledWith('a');
});

test('remove asks again before it acts', async () => {
  const { onRemove } = setUp();
  await userEvent.click(screen.getAllByRole('button', { name: 'Remove' })[0]);
  expect(onRemove).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole('button', { name: 'Remove it' }));
  expect(onRemove).toHaveBeenCalledWith('a');
});

test('the medium shown and a video not in H.265 are marked', () => {
  setUp('a');
  expect(screen.getByText('on screen').closest('tr')).toHaveTextContent('helix_qs8x6a0.75.mp4');
  expect(screen.getByText('not H.265').closest('tr')).toHaveTextContent('old.mp4');
});

test('downloads come from the server', () => {
  setUp();
  expect(screen.getAllByRole('link', { name: 'Download' })[0]).toHaveAttribute('href', '/api/media/a/content');
});

test('an empty library says how to fill it', () => {
  render(<MediaTable media={[]} shownId={null} currentId={null} selected={[]} disabled={false} contentUrl={() => ''}
                     onShow={() => {}} onMove={() => {}} onRename={() => Promise.resolve(true)} onRemove={() => {}} onSelect={() => {}} onSelectAll={() => {}} />);
  expect(screen.getByText(/upload a quilt or a video/)).toBeInTheDocument();
});

test('ticking a medium reports it, and unticking it too', async () => {
  const { onSelect } = setUp(null, ['b']);
  await userEvent.click(screen.getByRole('checkbox', { name: 'Select helix_qs8x6a0.75.mp4' }));
  expect(onSelect).toHaveBeenCalledWith('a', true);
  await userEvent.click(screen.getByRole('checkbox', { name: 'Select old.mp4' }));
  expect(onSelect).toHaveBeenCalledWith('b', false);
});

test('the header box selects all, and shows a part selected', async () => {
  const { onSelectAll } = setUp(null, ['b']);
  const all = screen.getByRole('checkbox', { name: 'Select all' });
  expect(all).toHaveProperty('indeterminate', true);
  await userEvent.click(all);
  expect(onSelectAll).toHaveBeenCalledWith(true);
});

// jsdom has no DataTransfer: what the handlers use of it.
function dataTransfer() {
  return { effectAllowed: '', dropEffect: '', setData: vi.fn(), setDragImage: vi.fn(), files: [] };
}

function drag(name: string, onto: string, below: boolean) {
  const transfer = dataTransfer();
  const row = screen.getByText(onto).closest('tr')!;
  fireEvent.dragStart(screen.getByLabelText(`Move ${name}`), { dataTransfer: transfer });
  // jsdom's rows are of no height, at 0: a pointer below 0 is in their lower half. Its drag events have no clientY.
  const over = createEvent.dragOver(row, { dataTransfer: transfer });
  Object.defineProperty(over, 'clientY', { value: below ? 1 : 0 });
  fireEvent(row, over);
  return { row, transfer };
}

test('a row dragged by its grip onto the upper half of another lands above it', () => {
  const { onMove, onShow } = setUp();
  const { row, transfer } = drag('knot_qs8x6a0.75.jpg', 'helix_qs8x6a0.75.mp4', false);
  expect(row).toHaveClass('drop-before');
  fireEvent.drop(row, { dataTransfer: transfer });
  expect(onMove).toHaveBeenCalledWith(['c', 'a', 'b']);
  expect(onShow).not.toHaveBeenCalled();
  expect(row).not.toHaveClass('drop-before');
});

test('a row dragged onto the lower half of another lands below it', () => {
  const { onMove } = setUp();
  const { row, transfer } = drag('helix_qs8x6a0.75.mp4', 'old.mp4', true);
  expect(row).toHaveClass('drop-after');
  fireEvent.drop(row, { dataTransfer: transfer });
  expect(onMove).toHaveBeenCalledWith(['b', 'a', 'c']);
});

test('a row dropped where it was, or a drag let go elsewhere, changes nothing', () => {
  const { onMove } = setUp();
  const { row, transfer } = drag('helix_qs8x6a0.75.mp4', 'old.mp4', false);
  fireEvent.drop(row, { dataTransfer: transfer });  // Above old.mp4: where it is already.
  drag('old.mp4', 'knot_qs8x6a0.75.jpg', true);
  fireEvent.dragEnd(screen.getByLabelText('Move old.mp4'));
  expect(onMove).not.toHaveBeenCalled();
  expect(screen.getByText('knot_qs8x6a0.75.jpg').closest('tr')).not.toHaveClass('drop-after');
});

test('a drag from outside the table, e.g. a file, is not a move', () => {
  const { onMove } = setUp();
  const row = screen.getByText('old.mp4').closest('tr')!;
  fireEvent.dragOver(row, { dataTransfer: dataTransfer() });
  fireEvent.drop(row, { dataTransfer: dataTransfer() });
  expect(row.className).not.toMatch(/drop/);
  expect(onMove).not.toHaveBeenCalled();
});

test('Alt and the arrow keys move the current row, and stop at the ends', async () => {
  const { onMove, onShow } = setUp('b');
  screen.getByRole('table').focus();
  await userEvent.keyboard('{Alt>}{ArrowUp}{/Alt}');
  expect(onMove).toHaveBeenLastCalledWith(['b', 'a', 'c']);
  await userEvent.keyboard('{Alt>}{ArrowDown}{/Alt}');
  expect(onMove).toHaveBeenLastCalledWith(['a', 'c', 'b']);
  expect(onShow).not.toHaveBeenCalled();
});

test('with nothing current, Alt and an arrow move nothing', async () => {
  const { onMove } = setUp();
  screen.getByRole('table').focus();
  await userEvent.keyboard('{Alt>}{ArrowDown}{/Alt}');
  expect(onMove).not.toHaveBeenCalled();
});

test('a row is renamed in place, without showing it', async () => {
  const { onRename, onShow, onMove } = setUp('a');
  await userEvent.click(screen.getByRole('button', { name: 'Rename old.mp4' }));
  await userEvent.click(screen.getByRole('textbox', { name: 'New name of old.mp4' }));
  await userEvent.keyboard('{ArrowDown}');
  await userEvent.clear(screen.getByRole('textbox'));
  await userEvent.keyboard('new.mp4{Enter}');
  expect(onRename).toHaveBeenCalledWith('b', 'new.mp4');
  expect(screen.queryByRole('textbox')).toBeNull();
  expect(onShow).not.toHaveBeenCalled();
  expect(onMove).not.toHaveBeenCalled();
});
