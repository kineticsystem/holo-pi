import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test, vi } from 'vitest';
import { medium } from '../test/FakeHoloPiApi';
import { GradeSourceSelect } from './GradeSourceSelect';

const SOURCES = [medium({ id: 'b', name: 'b.png' }), medium({ id: 'c', name: 'c.png' })];

test('a quilt chosen is reported', async () => {
  const onCopy = vi.fn();
  render(<GradeSourceSelect sources={SOURCES} copiedId={null} disabled={false} onCopy={onCopy} />);
  expect(screen.getByRole('combobox')).toHaveDisplayValue('Copy grade from…');
  await userEvent.selectOptions(screen.getByRole('combobox'), 'c.png');
  expect(onCopy).toHaveBeenCalledWith('c');
});

test('the quilt copied is shown, unless it is gone', () => {
  const { rerender } = render(<GradeSourceSelect sources={SOURCES} copiedId="b" disabled={false} onCopy={() => {}} />);
  expect(screen.getByRole('combobox')).toHaveDisplayValue('b.png');
  rerender(<GradeSourceSelect sources={[SOURCES[1]]} copiedId="b" disabled={false} onCopy={() => {}} />);
  expect(screen.getByRole('combobox')).toHaveDisplayValue('Copy grade from…');
});

test('with no other graded quilt, it is disabled and says why', () => {
  render(<GradeSourceSelect sources={[]} copiedId={null} disabled={false} onCopy={() => {}} />);
  expect(screen.getByRole('combobox')).toBeDisabled();
  expect(screen.getByRole('combobox')).toHaveAttribute('title', 'No other quilt is graded');
});
