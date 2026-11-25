// A number typed or stepped, with its unit, e.g. 10 seconds. While what is typed is not a number within its limits, it
// says so and nothing changes; leaving the field then puts the number back.
import { useState } from 'react';

type NumberFieldProps = {
  label: string;
  unit: string;
  value: number;
  min: number;
  max: number;
  /** Whether only whole numbers are taken. */
  whole?: boolean;
  disabled?: boolean;
  onChange: (value: number) => void;
};

export function NumberField({ label, unit, value, min, max, whole = false, disabled = false, onChange }: NumberFieldProps) {
  const [typed, setTyped] = useState<string | null>(null); // What is being typed, until the field is left.

  function handleChange(text: string) {
    setTyped(text);
    const next = parse(text);
    if (next !== null && next !== value) onChange(next);
  }

  function parse(text: string): number | null {
    const next = Number(text);
    return text.trim() !== '' && next >= min && next <= max && (!whole || Number.isInteger(next)) ? next : null;
  }

  return (
    <label className="number">
      <input type="number" aria-label={label} min={min} max={max} step={whole ? 1 : 'any'} value={typed ?? value}
             disabled={disabled} aria-invalid={typed !== null && parse(typed) === null}
             onChange={event => handleChange(event.target.value)} onBlur={() => setTyped(null)} />
      <span>{unit}</span>
    </label>
  );
}
