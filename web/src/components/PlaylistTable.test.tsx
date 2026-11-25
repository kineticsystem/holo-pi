import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test, vi } from 'vitest';
import { medium } from '../test/FakeHoloPiApi';
import type { PlaylistEntry } from '../services/HoloPiApi';
import { makeRows } from '../utils/playlistUtils';
import { PlaylistTable } from './PlaylistTable';

const media = [medium({ id: 'q', name: 'wasp.png', kind: 'quilt', duration: null }), medium({ id: 'v', name: 'helix.mp4' })];
const items: PlaylistEntry[] = [{ media_id: 'q', enabled: true, seconds: 5, loops: null }];

function setUp(entries = items, playingId: string | null = null) {
  const calls = { onEnable: vi.fn(), onEnableAll: vi.fn(), onSeconds: vi.fn(), onLoops: vi.fn() };
  render(<PlaylistTable rows={makeRows(media, { repeat: true, items: entries })} playingId={playingId} {...calls} />);
  return calls;
}

test('a quilt takes seconds, and a video times, once it is played', () => {
  const calls = setUp([...items, { media_id: 'v', enabled: true, seconds: null, loops: 2 }]);
  fireEvent.change(screen.getByLabelText('Seconds for wasp.png'), { target: { value: '8' } });
  expect(calls.onSeconds).toHaveBeenCalledWith('q', 8);
  fireEvent.change(screen.getByLabelText('Times for helix.mp4'), { target: { value: '4' } });
  expect(calls.onLoops).toHaveBeenCalledWith('v', 4);
  expect(screen.getByText('40 s')).toBeInTheDocument(); // Twice 20 seconds.
});

test('a medium not played cannot be set, and its box plays it', async () => {
  const calls = setUp();
  expect(screen.getByLabelText('Times for helix.mp4')).toBeDisabled();
  await userEvent.click(screen.getByLabelText('Play helix.mp4'));
  expect(calls.onEnable).toHaveBeenCalledWith('v', true);
});

test('one box plays them all', async () => {
  const calls = setUp();
  const all = screen.getByLabelText('Play all');
  expect(all).toBePartiallyChecked();
  await userEvent.click(all);
  expect(calls.onEnableAll).toHaveBeenCalledWith(true);
});

test('the medium playing is marked', () => {
  setUp(items, 'q');
  expect(screen.getByText('wasp.png').closest('tr')).toHaveAttribute('aria-current', 'true');
  expect(screen.getByText('helix.mp4').closest('tr')).not.toHaveAttribute('aria-current');
});

test('an empty library says what to do', () => {
  render(<PlaylistTable rows={[]} playingId={null} onEnable={vi.fn()} onEnableAll={vi.fn()} onSeconds={vi.fn()} onLoops={vi.fn()} />);
  expect(screen.getByText(/library is empty/)).toBeInTheDocument();
});
