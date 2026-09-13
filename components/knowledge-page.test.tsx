import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { KnowledgePage, KnowledgeEvidence } from './knowledge-page';
import { SearchPage } from './search-page';
import type { CaseView } from '@/lib/knowledge-api';

const mocks = vi.hoisted(() => ({ load: vi.fn(), search: vi.fn() }));
vi.mock('@/lib/knowledge-api', async (original) => ({
  ...(await original<object>()),
  loadKnowledge: mocks.load,
  searchCases: mocks.search,
}));
const example: CaseView = {
  entry: {
    asset_id: 'asset1',
    result_id: 'result1',
    original_filename: 'cinema.png',
    preview_url: '/image',
    tags: ['cinematic'],
    revision: 1,
    preview_text: '人工解释',
  },
  result: {
    id: 'result1',
    summary: 'AI摘要',
    intent: '',
    dimensions: [
      {
        code: 'style',
        label: '风格',
        observation: 'AI观察',
        interpretation: 'AI解释',
        confidence: 0.5,
        evidence: [],
      },
    ],
    tags: ['cinematic'],
    features: [],
    warnings: [],
    completionStatus: 'complete',
    provenance: { mode: 'real', profileVersion: '1', pipelineVersion: '1' },
    humanRevision: {
      revision: 1,
      dimensions: [
        {
          code: 'style',
          label: '风格',
          observation: '人工观察',
          interpretation: '人工解释',
          review_status: 'edit',
          feedback_id: 'f',
        },
      ],
    },
    feedbackHistory: [
      {
        id: 'f',
        result_id: 'result1',
        revision: 1,
        feedback_type: 'edit',
        target_path: '/dimensions/style',
        original_value: 'AI解释',
        corrected_value: '人工解释',
        error_category: null,
        comment: '校准备注',
        base_revision: 0,
        created_at: '2026-09-10T10:00:00Z',
      },
    ],
  },
};
beforeEach(() => {
  sessionStorage.clear();
  vi.clearAllMocks();
  mocks.load.mockResolvedValue([example]);
  mocks.search.mockResolvedValue([example.entry]);
});

it('shows real review differences, case link, filters and honest missing tag fields', async () => {
  render(<KnowledgePage />);
  await screen.findByRole('link', { name: 'cinema.png' });
  expect(screen.getByRole('link', { name: 'cinema.png' })).toHaveAttribute(
    'href',
    '/knowledge/result1',
  );
  expect(screen.getByText('AI 分析：AI解释')).toBeInTheDocument();
  expect(screen.getByText('人工校准：人工解释')).toBeInTheDocument();
  expect(screen.getByText('备注：校准备注')).toBeInTheDocument();
  expect(screen.getByText(/未提供独立的逐标签审核字段/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('按审核状态筛选'), {
    target: { value: '已确认' },
  });
  expect(
    screen.queryByRole('link', { name: 'cinema.png' }),
  ).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('按审核状态筛选'), {
    target: { value: '已人工修改' },
  });
  fireEvent.change(screen.getByLabelText('按标签筛选'), {
    target: { value: 'cinematic' },
  });
  expect(screen.getByRole('link', { name: 'cinema.png' })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('搜索案例'), {
    target: { value: 'no match' },
  });
  expect(
    screen.queryByRole('link', { name: 'cinema.png' }),
  ).not.toBeInTheDocument();
});

it('shows missing review data and allows load failures to retry', async () => {
  mocks.load.mockRejectedValueOnce(new Error('offline'));
  render(<KnowledgePage />);
  await screen.findByRole('alert');
  fireEvent.click(screen.getByRole('button', { name: '刷新' }));
  await screen.findByRole('link', { name: 'cinema.png' });
});

it('does not invent human review when fields are absent', () => {
  render(
    <KnowledgeEvidence
      result={{
        ...example.result!,
        humanRevision: undefined,
        feedbackHistory: [],
      }}
      full
    />,
  );
  expect(screen.getAllByText(/暂无人工审核记录/).length).toBeGreaterThan(0);
  expect(screen.queryByText('人工校准：人工解释')).not.toBeInTheDocument();
});

it('does not preload images, sends filters after search and shows provider errors', async () => {
  render(<SearchPage />);
  expect(mocks.search).not.toHaveBeenCalled();
  expect(mocks.load).not.toHaveBeenCalled();
  expect(screen.queryByRole('img')).not.toBeInTheDocument();
  expect(screen.queryByLabelText('检索方式')).not.toBeInTheDocument();
  expect(screen.queryByRole('link', { name: '审美档案' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '检索' }));
  await screen.findByRole('link', { name: 'cinema.png' });
  expect(
    screen.getByRole('img', { name: 'cinema.png 缩略图' }),
  ).toHaveAttribute('src', '/image');
  fireEvent.click(screen.getByText('高级筛选'));
  fireEvent.change(screen.getByLabelText('查询'), {
    target: { value: '冷静' },
  });
  fireEvent.change(screen.getByLabelText('标签（逗号分隔）'), {
    target: { value: 'cinematic' },
  });
  fireEvent.change(screen.getByLabelText('数值字段'), {
    target: { value: 'shadow_occupancy' },
  });
  fireEvent.change(screen.getByLabelText('数值'), { target: { value: '0.4' } });
  mocks.search.mockRejectedValueOnce(
    new Error('SEMANTIC_SEARCH_NOT_CONFIGURED'),
  );
  fireEvent.click(screen.getByRole('button', { name: '检索' }));
  await waitFor(() =>
    expect(mocks.search).toHaveBeenLastCalledWith('hybrid', {
      query: '冷静',
      tags: ['cinematic'],
      numeric_filters: [{ field: 'shadow_occupancy', op: 'gte', value: 0.4 }],
      limit: 50,
      min_similarity: 0.3,
    }, expect.any(Function)),
  );
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'SEMANTIC_SEARCH_NOT_CONFIGURED',
  );
});

it('paginates returned thumbnails without another whole-library request and shows zero results', async () => {
  mocks.search.mockResolvedValueOnce(Array.from({ length: 15 }, (_, i) => ({ ...example.entry, result_id: `r${i}`, original_filename: `case${i}.png` })));
  render(<SearchPage />);
  fireEvent.click(screen.getByRole('button', { name: '检索' }));
  await screen.findByText('找到 15 个案例');
  expect(screen.getAllByRole('img')).toHaveLength(12);
  fireEvent.click(screen.getByRole('button', { name: '加载更多' }));
  expect(screen.getAllByRole('img')).toHaveLength(15);
  expect(mocks.search).toHaveBeenCalledTimes(1);
  expect(mocks.load).not.toHaveBeenCalled();
  mocks.search.mockResolvedValueOnce([]);
  fireEvent.click(screen.getByRole('button', { name: '检索' }));
  await screen.findByText('暂无满足条件和相关性门槛的案例。');
  expect(screen.queryByRole('img')).not.toBeInTheDocument();
});
