import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test, vi } from 'vitest';
import { UploadForm } from './UploadForm';

const files = () => [new File(['a'], 'a.png', { type: 'image/png' }), new File(['b'], 'b.mp4', { type: 'video/mp4' })];

test('files dropped are reported with the layout typed, and the form asks nothing else', async () => {
  const onFiles = vi.fn();
  render(<UploadForm onFiles={onFiles} />);
  await userEvent.type(screen.getByLabelText('Columns'), '8');
  await userEvent.type(screen.getByLabelText('Rows'), '6');
  const dropped = files();
  fireEvent.drop(screen.getByRole('button', { name: /Drop files here/ }), { dataTransfer: { files: dropped } });
  expect(onFiles).toHaveBeenCalledWith(dropped, { columns: 8, rows: 6 });
  expect(screen.queryAllByRole('checkbox')).toEqual([]);
});

test('files chosen are reported too, without a layout when none is typed', async () => {
  const onFiles = vi.fn();
  render(<UploadForm onFiles={onFiles} />);
  const chosen = files();
  await userEvent.upload(screen.getByTestId('dropzone-input'), chosen);
  expect(onFiles).toHaveBeenCalledWith(chosen, { columns: null, rows: null });
});
