import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ComputationalFeatures } from './computational-features';
import type { FeatureResult } from '@/lib/aesthetic-domain';

function feature(code: string, values: Record<string, unknown>, status: FeatureResult['status'] = 'succeeded'): FeatureResult {
  return { extractor_code: code, extractor_version: '1.0.0', feature_schema_version: '1.0.0', method: 'fixture method', standard: 'fixture standard', status, parameters: { bins: 32 }, values, artifacts: [], provenance: { profile_source: 'assumed sRGB', reference_white: 'D65' }, warnings: [], error_detail: status === 'failed' ? 'fixture failure' : null };
}

const apiResponse = {
  completion_status: 'complete' as const,
  warnings: ['ICC_PROFILE_MISSING_ASSUMED_SRGB'],
  features: [
    feature('cie_lightness', { mean: 53.585, median: 52.125, p01: 1, p99: 99 }),
    feature('global_tonal_contrast', { lstar_p95_p05_span: 81.25, lstar_iqr: 42.5, lstar_standard_deviation: 24.75 }),
    feature('multiscale_local_contrast', { scales: [{ scale_fraction: 0.03125, energy_rms: 0.1875 }] }),
    feature('tonal_occupancy', { configuration_version: '1.0.0', shadow_lstar_max: 20, highlight_lstar_min: 80, shadow_share: 0.45, midtone_share: 0.4, highlight_share: 0.15 }),
  ],
};

describe('ComputationalFeatures', () => {
  it('renders concrete values from a non-empty API features response', () => {
    render(<ComputationalFeatures features={apiResponse.features} completionStatus={apiResponse.completion_status} resultWarnings={apiResponse.warnings} />);
    expect(screen.getByRole('region', { name: '真实计算' })).toBeInTheDocument();
    expect(screen.getByText('平均感知明度 L*')).toBeInTheDocument();
    expect(screen.getByText('53.5850')).toBeInTheDocument();
    expect(screen.getByText('全局色调跨度 p95-p05')).toBeInTheDocument();
    expect(screen.getByText('81.2500')).toBeInTheDocument();
    expect(screen.getByText('RMS 0.1875')).toBeInTheDocument();
    expect(screen.getByText('Tone distribution · 明暗层级')).toBeInTheDocument();
    expect(screen.getByText('45.0%')).toBeInTheDocument();
    expect(screen.getByText('40.0%')).toBeInTheDocument();
    expect(screen.getByText('15.0%')).toBeInTheDocument();
  });

  it('shows successful values and failed extractors for a partial result', () => {
    render(<ComputationalFeatures features={[...apiResponse.features, feature('fixture_failure', {}, 'failed')]} completionStatus="partial" resultWarnings={[]} />);
    expect(screen.getByText('当前结果状态：partial')).toBeInTheDocument();
    expect(screen.getByText('52.1250')).toBeInTheDocument();
    expect(screen.getByText(/提取失败 · fixture_failure：fixture failure/)).toBeInTheDocument();
  });

  it('shows an explicit error instead of a silent blank for empty features', () => {
    render(<ComputationalFeatures features={[]} completionStatus="complete" resultWarnings={[]} />);
    expect(screen.getByRole('alert')).toHaveTextContent('真实特征结果缺失');
    expect(screen.getByRole('alert')).toHaveTextContent('不能视为完整成功');
  });
});
