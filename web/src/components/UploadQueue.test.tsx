import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test, vi } from 'vitest';
import type { UploadJob } from '../hooks/useUploads';
import { medium } from '../test/FakeHoloPiApi';
import { UploadQueue } from './UploadQueue';

function job(id: number, name: string, status: UploadJob['status'], fields: Partial<UploadJob> = {}): UploadJob {
  return { id, file: new File(['x'], name), options: { columns: null, rows: null, reverse: false, play: false },
           status, progress: 0, error: null, medium: null, ...fields };
}

test('each file shows its state, and the one sending its progress', () => {
  render(<UploadQueue jobs={[job(1, 'a.mp4', 'done', { medium: medium({ warning: 'not H.265' }) }),
                             job(2, 'b.mp4', 'sending', { progress: 40 }), job(3, 'c.png', 'failed', { error: 'no layout' })]}
                      onCancel={() => {}} onCancelAll={() => {}} onClear={() => {}} />);
  expect(screen.getByText('kept, with a warning')).toBeInTheDocument();
  expect(screen.getByText('sending 40%')).toBeInTheDocument();
  expect(screen.getByRole('progressbar', { name: 'Sending b.mp4' })).toHaveAttribute('value', '40');
  expect(screen.getByText('no layout')).toBeInTheDocument();
  expect(screen.getByText('not H.265')).toBeInTheDocument();
});

test('stop reports the file, and only running files can be stopped', async () => {
  const onCancel = vi.fn();
  render(<UploadQueue jobs={[job(1, 'a.mp4', 'done'), job(2, 'b.mp4', 'waiting')]}
                      onCancel={onCancel} onCancelAll={() => {}} onClear={() => {}} />);
  expect(screen.queryByRole('button', { name: 'Stop a.mp4' })).toBeNull();
  await userEvent.click(screen.getByRole('button', { name: 'Stop b.mp4' }));
  expect(onCancel).toHaveBeenCalledWith(2);
});

test('each video not in H.265 has its warning, and the queue counts them', () => {
  const warning = 'The video is h264, not H.265 (HEVC)';
  render(<UploadQueue jobs={[job(1, 'a.mp4', 'done', { medium: medium({ warning }) }), job(2, 'b.mp4', 'done', { medium: medium() }),
                             job(3, 'c.mp4', 'done', { medium: medium({ warning }) })]}
                      onCancel={() => {}} onCancelAll={() => {}} onClear={() => {}} />);
  expect(screen.getByRole('status')).toHaveTextContent('2 of the files are not in H.265 (HEVC)');
  expect(screen.getAllByText(warning)).toHaveLength(2);
  expect(screen.getAllByText('kept, with a warning')).toHaveLength(2);
  expect(screen.getByText('kept')).toBeInTheDocument();
});
