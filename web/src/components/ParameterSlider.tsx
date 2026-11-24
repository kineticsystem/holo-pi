// A named value set with a slider, e.g. Exposure +0.50. A double click on it puts the default back.
import type { GradeParameter } from '../services/HoloPiApi';
import { formatValue } from '../utils/gradeUtils';

type ParameterSliderProps = { parameter: GradeParameter; value: number; onChange: (value: number) => void };

export function ParameterSlider({ parameter, value, onChange }: ParameterSliderProps) {
  return (
    <label className={value === parameter.default ? 'slider' : 'slider changed'}
           title={`${parameter.description} Double-click to reset.`}
           onDoubleClick={() => onChange(parameter.default)}>
      <span>{parameter.label}</span>
      <output>{formatValue(value, parameter)}</output>
      <input type="range" min={parameter.minimum} max={parameter.maximum} step={10 ** -parameter.decimals} value={value}
             onChange={event => onChange(Number(event.target.value))} />
    </label>
  );
}
