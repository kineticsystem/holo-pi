// What the grading page shows of a grade's parameters: their sections, as the server orders them, and their values in
// words. Used by useGrade and the sliders.
import type { GradeParameter } from '../services/HoloPiApi';

export type Tool = { parameter: GradeParameter; value: number };
export type Section = { title: string; tools: Tool[]; changed: boolean };

/** The parameters by section, each with its value, or its default when it has none. */
export function groupBySection(parameters: GradeParameter[], values: Record<string, number>): Section[] {
  const sections: Section[] = [];
  for (const parameter of parameters) {
    const value = values[parameter.id] ?? parameter.default;
    let section = sections.find(s => s.title === parameter.section);
    if (!section) {
      section = { title: parameter.section, tools: [], changed: false };
      sections.push(section);
    }
    section.tools.push({ parameter, value });
    section.changed ||= value !== parameter.default;
  }
  return sections;
}

/** A value as it is shown, e.g. +0.50: with a sign when the slider goes both ways. */
export function formatValue(value: number, parameter: GradeParameter): string {
  const text = value.toFixed(parameter.decimals);
  return parameter.minimum < 0 && value > 0 ? `+${text}` : text;
}
