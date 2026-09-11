import { describe, expect, it } from 'vitest';

import {
  formatFeatureNumber,
  formatFeatureValue,
} from './feature-value-format';

describe('feature value formatting', () => {
  it('formats ratios as one-decimal percentages and continuous metrics to two decimals', () => {
    expect(formatFeatureNumber(0.12356, 'shadow_share')).toBe('12.4%');
    expect(formatFeatureNumber(0.45678, 'alpha_coverage')).toBe('45.7%');
    expect(formatFeatureNumber(53.585, 'mean')).toBe('53.59');
    expect(formatFeatureNumber(17, 'sample_count')).toBe('17');
  });

  it('formats nested technical values without changing the source object', () => {
    const source = { shadow_share: 0.12356, mean: 53.585 };
    expect(formatFeatureValue(source)).toBe(
      '{"shadow_share":12.4%,"mean":53.59}',
    );
    expect(source).toEqual({ shadow_share: 0.12356, mean: 53.585 });
  });
});
