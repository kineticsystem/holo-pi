// A section of the grading tools, e.g. Light: its sliders, under a title that folds them, marked when one is changed.
import type { Section } from '../utils/gradeUtils';
import { ParameterSlider } from './ParameterSlider';

type ToolSectionProps = { section: Section; open: boolean; onChange: (parameter: string, value: number) => void };

export function ToolSection({ section, open, onChange }: ToolSectionProps) {
  return (
    <details className="tools" open={open}>
      <summary>
        {section.title}
        {section.changed && <span className="badge">changed</span>}
      </summary>
      {section.tools.map(({ parameter, value }) => (
        <ParameterSlider key={parameter.id} parameter={parameter} value={value}
                         onChange={next => onChange(parameter.id, next)} />
      ))}
    </details>
  );
}
