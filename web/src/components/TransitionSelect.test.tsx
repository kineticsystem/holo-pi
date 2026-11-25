import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test, vi } from 'vitest';
import type { Transition } from '../services/HoloPiApi';
import { TransitionSelect } from './TransitionSelect';

function setUp(transition: Transition, why: string | null = null) {
  const calls = { onTransition: vi.fn(), onSeconds: vi.fn() };
  render(<TransitionSelect transition={transition} seconds={1} disabled={false} why={why} {...calls} />);
  return calls;
}

test('a transition is chosen by its name', async () => {
  const calls = setUp('cut');
  expect(screen.queryByLabelText('Seconds of the transition')).not.toBeInTheDocument();
  await userEvent.selectOptions(screen.getByLabelText('Transition'), 'Fade through black');
  expect(calls.onTransition).toHaveBeenCalledWith('fade through black');
});

test('one that takes time says how long, and takes fractions of a second', () => {
  const calls = setUp('cross fade');
  fireEvent.change(screen.getByLabelText('Seconds of the transition'), { target: { value: '0.5' } });
  expect(calls.onSeconds).toHaveBeenCalledWith(0.5);
});

test('without the GPU there are none, and it says why', () => {
  setUp('cross fade', 'Transitions need the GPU: --screen gl');
  expect(screen.getByLabelText('Transition')).toBeDisabled();
  expect(screen.getByLabelText('Transition')).toHaveValue('cut');
  expect(screen.getByTitle(/need the GPU/)).toBeInTheDocument();
  expect(screen.queryByLabelText('Seconds of the transition')).not.toBeInTheDocument();
});
