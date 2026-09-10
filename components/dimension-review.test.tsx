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
  feedbackHistory: [],
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
      error_category: null,
    }),
  );
  expect(dimension.observation).toBe('模型观察');
});

it('renders newest-first history and counts only the current dimension', () => {
  const reviewed = {
    ...result,
    humanRevision: { ...result.humanRevision!, revision: 5 },
    feedbackHistory: [
      {
        id: 'lighting-new',
        result_id: 'result-id',
        revision: 5,
        feedback_type: 'reject' as const,
        created_at: '2026-09-09T02:00:00Z',
        target_path: '/dimensions/lighting',
        original_value: {},
        corrected_value: null,
        error_category: null,
        comment: 'other dimension',
        base_revision: 4,
      },
      {
        id: 'color-new',
        result_id: 'result-id',
        revision: 4,
        feedback_type: 'edit' as const,
        created_at: '2026-09-09T01:00:00Z',
        target_path: '/dimensions/color',
        original_value: 'old',
        corrected_value: 'new',
        error_category: 'wording',
        comment: 'keep this note',
        base_revision: 3,
      },
      {
        id: 'color-old',
        result_id: 'result-id',
        revision: 1,
        feedback_type: 'accept' as const,
        created_at: '2026-09-09T00:00:00Z',
        target_path: '/dimensions/color/observation',
        original_value: 'old',
        corrected_value: null,
        error_category: null,
        comment: null,
        base_revision: 0,
      },
    ],
  };
  render(
    <DimensionReview
      result={reviewed}
      dimension={dimension}
      save={vi.fn()}
      onSaved={vi.fn()}
    />,
  );
  expect(screen.getByText(/人工审核：未确认 · 修订 2/)).toBeInTheDocument();
  expect(screen.getByText(/Review history（2）/)).toBeInTheDocument();
  expect(screen.getByText('备注：keep this note')).toBeInTheDocument();
  expect(screen.queryByText('备注：other dimension')).not.toBeInTheDocument();
  const entries = screen.getAllByText(/· rev [14]$/);
  expect(entries[0]).toHaveTextContent('rev 4');
  expect(entries[1]).toHaveTextContent('rev 1');
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
  expect(
    screen.queryByRole('button', { name: '拒绝' }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '确认' }));
  await waitFor(() =>
    expect(screen.getByRole('alert')).toHaveTextContent('REVISION_CONFLICT'),
  );
  expect(onSaved).not.toHaveBeenCalled();
});

it('restores human revision from server independently of the original text', () => {
  const restored = {
    ...result,
    feedbackHistory: [1, 2, 3]
      .map((revision) => ({
        id: `feedback-${revision}`,
        result_id: 'result-id',
        revision,
        feedback_type: 'edit' as const,
        created_at: `2026-09-09T0${revision}:00:00Z`,
        target_path: '/dimensions/color',
        original_value: {},
        corrected_value: {},
        error_category: null,
        comment: null,
        base_revision: revision - 1,
      }))
      .reverse(),
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
