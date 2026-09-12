import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import type { AnalysisResult } from '@/lib/aesthetic-domain';
import { SemanticStatus } from './semantic-status';
import { SpaceComputationalFeatures } from './spatial-composition-features';

it('shows failed semantics alongside retained successful calculations', () => {
  const result = {
    provenance: {
      mode: 'real',
      pipelineVersion: '1.1.0',
      semantic: { status: 'failed' },
    },
    warnings: ['MODEL_TIMEOUT'],
    dimensions: [],
    features: [
      {
        extractor_code: 'space_structure',
        status: 'succeeded',
        values: {
          spatial_complexity: { score: 0.625 },
          empty_space_ratio: 0.35,
        },
      },
    ],
  } as unknown as AnalysisResult;
  render(
    <>
      <SemanticStatus result={result} />
      <SpaceComputationalFeatures features={result.features} />
    </>,
  );
  expect(screen.getByText(/模型调用失败/)).toBeInTheDocument();
  const warning = screen.getByText('MODEL_TIMEOUT');
  expect(warning).not.toBeVisible();
  expect(warning.closest('details')).not.toHaveAttribute('open');
  warning.closest('details')!.open = true;
  expect(warning).toBeVisible();
  expect(screen.getByText('0.63')).toBeInTheDocument();
});

it('renders model uncertainty from provenance', () => {
  const result = {
    provenance: {
      mode: 'real',
      pipelineVersion: '1.1.0',
      semantic: { status: 'succeeded', uncertainty: { style: '风格证据不足' } },
    },
    warnings: [],
    dimensions: [{ code: 'style', label: '风格' }],
  } as unknown as AnalysisResult;
  render(<SemanticStatus result={result} />);
  expect(screen.getByText('不确定性 · 风格：风格证据不足')).toBeInTheDocument();
});
