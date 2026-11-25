import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { expect, test, vi } from 'vitest';
import { NumberField } from './NumberField';

function setUp(whole = false) {
  const onChange = vi.fn();
  function Field() {
    const [value, setValue] = useState(10);
    return <NumberField label="Seconds" unit="seconds" value={value} min={1} max={100} whole={whole}
                        onChange={next => { onChange(next); setValue(next); }} />;
  }
  render(<Field />);
  return { onChange, field: screen.getByLabelText('Seconds') };
}

test('a number typed is reported', async () => {
  const { onChange, field } = setUp();
  await userEvent.clear(field);
  await userEvent.type(field, '25');
  expect(onChange).toHaveBeenLastCalledWith(25);
});

test('an empty field or one out of its limits changes nothing, says so, and goes back when left', async () => {
  const { onChange, field } = setUp();
  await userEvent.clear(field);
  expect(field).toHaveAttribute('aria-invalid', 'true');
  await userEvent.type(field, '0');
  expect(onChange).not.toHaveBeenCalled();
  await userEvent.tab();
  expect(field).toHaveValue(10);
  expect(field).toHaveAttribute('aria-invalid', 'false');
});

test('a whole number takes no fraction', async () => {
  const { onChange, field } = setUp(true);
  await userEvent.clear(field);
  await userEvent.type(field, '2.5');
  expect(onChange).not.toHaveBeenCalledWith(2.5);
  expect(field).toHaveAttribute('aria-invalid', 'true');
});
