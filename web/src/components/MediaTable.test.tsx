import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test, vi } from 'vitest';
import { medium } from '../test/FakeHoloPiApi';
import { MediaTable } from './MediaTable';

function setUp(shownId: string | null = null, selected: string[] = [], currentId: string | null = shownId) {
  const onShow = vi.fn();
  const onRemove = vi.fn();
  const onSelect = vi.fn();
  const onSelectAll = vi.fn();
  render(<MediaTable media={[medium({ id: 'a', name: 'helix_qs8x6a0.75.mp4' }), medium({ id: 'b', name: 'old.mp4', codec: 'h264', warning: 'not H.265' })]}
                     shownId={shownId} currentId={currentId} selected={selected} disabled={false} contentUrl={id => `/api/media/${id}/content`}
                     onShow={onShow} onRemove={onRemove} onSelect={onSelect} onSelectAll={onSelectAll} />);
  return { onShow, onRemove, onSelect, onSelectAll };
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
                     onShow={() => {}} onRemove={() => {}} onSelect={() => {}} onSelectAll={() => {}} />);
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
