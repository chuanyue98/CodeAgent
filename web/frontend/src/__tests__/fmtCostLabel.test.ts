import { describe, expect, test } from 'vitest';
import { fmtCostLabel } from '../api/analytics';

describe('fmtCostLabel', () => {
  test('a fully priced figure is a plain amount', () => {
    expect(fmtCostLabel(1.5, 0, 'Unpriced')).toBe('$1.50');
    expect(fmtCostLabel(1.5, undefined, 'Unpriced')).toBe('$1.50');
  });

  test('a figure that leaves tokens out is marked as a lower bound', () => {
    expect(fmtCostLabel(1.5, 100, 'Unpriced')).toBe('$1.50+');
  });

  test('no priced tokens at all reads as unpriced, not as free', () => {
    expect(fmtCostLabel(0, 100, 'Unpriced')).toBe('Unpriced');
  });
});
