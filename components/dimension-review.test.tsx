import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { DimensionReview } from './dimension-review';
import type { AnalysisResult } from '@/lib/aesthetic-domain';

const dimension = {
  code: 'color',
  label: '色彩',
  observation: '模型观察',
  interpretation: '模型解释',
  confidence: 0.5,
  evidence: ['feature:cie_chroma#/mean'],
};
const result: AnalysisResult = {
  id: 'result-id',
  summary: '',
  intent: '',
  dimensions: [dimension],
  tags: [],
  provenance: { mode: 'real', profileVersion: '1', pipelineVersion: '1' },
  features: [],
  warnings: [],
  completionStatus: 'complete',
  humanRevision: {
    revision: 0,
    dimensions: [
      { ...dimension, review_status: 'unreviewed', feedback_id: null },
    ],
  },
  resolvedEvidence: [
    {
      id: dimension.evidence[0],
      label: '平均彩度 C*ab',
      value: 42.25,
      status: 'resolved',
      supports_dimensions: ['color'],
    },
  ],
};

it('renders resolved evidence and submits dimension edits without mutating original', async () => {
  const save = vi.fn().mockResolvedValue(result);
  const onSaved = vi.fn();
  render(
    <DimensionReview
      result={result}
      dimension={dimension}
      save={save}
      onSaved={onSaved}
    />,
  );
  expect(screen.getByText('平均彩度 C*ab：42.25')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '修改' }));
  fireEvent.change(screen.getByLabelText('修改观察'), {
    target: { value: '人工观察' },
  });
  fireEvent.change(screen.getByLabelText('修改解释'), {
    target: { value: '人工解释' },
  });
  fireEvent.change(screen.getByLabelText('反馈备注'), {
    target: { value: '备注' },
  });
  fireEvent.click(screen.getByRole('button', { name: '保存修订' }));
  await waitFor(() => expect(onSaved).toHaveBeenCalledWith(result));
  expect(save).toHaveBeenCalledWith(
    'result-id',
    expect.objectContaining({
      feedback_type: 'edit',
      target_path: '/dimensions/color',
      base_revision: 0,
      corrected_value: { observation: '人工观察', interpretation: '人工解释' },
      comment: '备注',
    }),
  );
  expect(dimension.observation).toBe('模型观察');
});

it('does not claim success on failed save and shows invalid refs explicitly', async () => {
  const onSaved = vi.fn();
  const invalid = {
    ...result,
    resolvedEvidence: [
      { ...result.resolvedEvidence![0], status: 'invalid' as const },
    ],
  };
  render(
    <DimensionReview
      result={invalid}
      dimension={dimension}
      save={vi.fn().mockRejectedValue(new Error('REVISION_CONFLICT'))}
      onSaved={onSaved}
    />,
  );
  expect(screen.getByText(/引用无效，无法解析/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '拒绝' }));
  await waitFor(() =>
    expect(screen.getByRole('alert')).toHaveTextContent('REVISION_CONFLICT'),
  );
  expect(onSaved).not.toHaveBeenCalled();
});

it('restores human revision from server independently of the original text', () => {
  const restored = {
    ...result,
    humanRevision: {
      revision: 3,
      dimensions: [
        {
          ...dimension,
          observation: '历史人工观察',
          interpretation: '历史人工解释',
          review_status: 'edit' as const,
          feedback_id: 'feedback-id',
        },
      ],
    },
  };
  render(
    <DimensionReview
      result={restored}
      dimension={dimension}
      save={vi.fn()}
      onSaved={vi.fn()}
    />,
  );
  expect(
    screen.getByText(/最新人工版本 · 观察：历史人工观察/),
  ).toBeInTheDocument();
  expect(screen.getByText(/已修订 · 修订 3/)).toBeInTheDocument();
  expect(dimension.interpretation).toBe('模型解释');
});
