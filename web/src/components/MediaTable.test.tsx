import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test, vi } from 'vitest';
import { medium } from '../test/FakeHoloPiApi';
import { MediaTable } from './MediaTable';

function setUp(shownId: string | null = null, selected: string[] = []) {
  const onPlay = vi.fn();
  const onRemove = vi.fn();
  const onSelect = vi.fn();
  const onSelectAll = vi.fn();
  render(<MediaTable media={[medium({ id: 'a', name: 'helix_qs8x6a0.75.mp4' }), medium({ id: 'b', name: 'old.mp4', codec: 'h264', warning: 'not H.265' })]}
                     shownId={shownId} selected={selected} disabled={false} contentUrl={id => `/api/media/${id}/content`}
                     onPlay={onPlay} onRemove={onRemove} onSelect={onSelect} onSelectAll={onSelectAll} />);
  return { onPlay, onRemove, onSelect, onSelectAll };
}

test('play reports the medium', async () => {
  const { onPlay } = setUp();
  await userEvent.click(screen.getAllByRole('button', { name: 'Play' })[1]);
  expect(onPlay).toHaveBeenCalledWith('b');
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
  render(<MediaTable media={[]} shownId={null} selected={[]} disabled={false} contentUrl={() => ''}
                     onPlay={() => {}} onRemove={() => {}} onSelect={() => {}} onSelectAll={() => {}} />);
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
