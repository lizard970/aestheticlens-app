import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { FeatureResult } from '@/lib/aesthetic-domain';
import {
  CompositionComputationalFeatures,
  SpaceComputationalFeatures,
} from './spatial-composition-features';

function feature(code: string, values: Record<string, unknown>): FeatureResult {
  return {
    extractor_code: code,
    extractor_version: '1.0.0',
    feature_schema_version: '1.0.0',
    method: 'fixture method',
    standard: null,
    status: 'succeeded',
    parameters: {},
    values,
    artifacts: [],
    provenance: {},
    warnings: [],
    error_detail: null,
  };
}

const features = [
  feature('space_structure', {
    spatial_complexity: { score: 0.625, edge_density: 0.2 },
    empty_space_ratio: 0.35,
    foreground_background_hint: {
      status: 'available',
      hint: 'center_sharper_than_surround',
    },
    depth_layer_hint: {
      status: 'available',
      hint: 'vertical_focus_gradient_detected',
      band_focus_signal: { top: 0.01, middle: 0.03, bottom: 0.02 },
    },
  }),
  feature('composition_geometry', {
    subject_position_hint: { status: 'available', hint: 'upper_right' },
    visual_center_offset: { status: 'available', normalized_distance: 0.25 },
    negative_space_ratio: 0.35,
    symmetry_score: { left_right: 0.8, top_bottom: 0.6, mean: 0.7 },
    rule_of_thirds_score: { status: 'available', score: 0.9 },
  }),
];

describe('spatial and composition real feature panels', () => {
  it('renders concrete space values from the API feature', () => {
    render(<SpaceComputationalFeatures features={features} />);

    expect(
      screen.getByRole('region', { name: '空间真实计算' }),
    ).toBeInTheDocument();
    expect(screen.getByText('空间复杂度')).toBeInTheDocument();
    expect(screen.getByText('0.63')).toBeInTheDocument();
    expect(screen.getByText('35.0%')).toBeInTheDocument();
    expect(screen.getByText('检测到纵向清晰度梯度')).toBeInTheDocument();
  });

  it('renders concrete composition values from the API feature', () => {
    render(<CompositionComputationalFeatures features={features} />);

    expect(
      screen.getByRole('region', { name: '构图真实计算' }),
    ).toBeInTheDocument();
    expect(screen.getByText('右上')).toBeInTheDocument();
    expect(screen.getByText('视觉中心偏移')).toBeInTheDocument();
    expect(screen.getByText('0.25')).toBeInTheDocument();
    expect(screen.getByText('0.90')).toBeInTheDocument();
  });

  it('does not silently hide a missing API feature', () => {
    render(<SpaceComputationalFeatures features={[]} />);

    expect(screen.getByRole('alert')).toHaveTextContent('空间真实计算不可用');
  });
});
