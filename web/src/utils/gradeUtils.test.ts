import { expect, test } from 'vitest';
import { PARAMETERS } from '../test/FakeHoloPiApi';
import { formatValue, groupBySection } from './gradeUtils';

test('the parameters are in their sections, in order, with their values or their defaults', () => {
  const sections = groupBySection(PARAMETERS, { exposure: 1 });
  expect(sections.map(s => [s.title, s.tools.map(t => [t.parameter.id, t.value]), s.changed])).toEqual([
    ['Color', [['saturation', 0]], false],
    ['Light', [['exposure', 1], ['contrast', 0]], true],
    ['Effects', [['sharpness', 0]], false],
  ]);
});

test('a value is shown with its decimals, and a sign when it goes both ways', () => {
  const [, exposure, contrast, sharpness] = PARAMETERS;
  expect([formatValue(0.5, exposure), formatValue(0, exposure), formatValue(-3, contrast),
          formatValue(40, sharpness)]).toEqual(['+0.50', '0.00', '-3', '40']);
});
