import { fireEvent, render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import { PARAMETERS } from '../test/FakeHoloPiApi';
import { ParameterSlider } from './ParameterSlider';

const EXPOSURE = PARAMETERS[1];

test('the slider says its value, and each move of it', () => {
  const onChange = vi.fn();
  render(<ParameterSlider parameter={EXPOSURE} value={0.5} onChange={onChange} />);
  expect(screen.getByText('+0.50')).toBeInTheDocument();
  const slider = screen.getByRole('slider');
  expect(slider).toHaveAttribute('step', '0.01');
  fireEvent.change(slider, { target: { value: '1.25' } });
  expect(onChange).toHaveBeenCalledWith(1.25);
});

test('a double click puts the default back', () => {
  const onChange = vi.fn();
  render(<ParameterSlider parameter={EXPOSURE} value={2} onChange={onChange} />);
  fireEvent.doubleClick(screen.getByRole('slider'));
  expect(onChange).toHaveBeenCalledWith(0);
});
