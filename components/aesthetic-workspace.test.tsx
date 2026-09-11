import {
  fireEvent,
  act,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import type { AnalysisResult } from '@/lib/aesthetic-domain';
import {
  emptyQueue,
  nextReview,
  reviewStatus,
  type ReviewQueue,
} from '@/lib/review-queue';
import { AestheticWorkspace } from './aesthetic-workspace';

const mocks = vi.hoisted(() => ({
  read: vi.fn(),
  write: vi.fn(),
  analyze: vi.fn(),
  retry: vi.fn(),
  get: vi.fn(),
  save: vi.fn(),
}));
vi.mock('@/lib/review-queue', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  readQueue: mocks.read,
  writeQueue: mocks.write,
}));
vi.mock('@/lib/api-analysis-provider', () => ({
  ApiAnalysisProvider: class {
    analyze = mocks.analyze;
    analyzeExisting = mocks.retry;
    getResult = mocks.get;
    saveFeedback = mocks.save;
    history = vi.fn().mockResolvedValue([]);
  },
}));

function result(id: string, done = false): AnalysisResult {
  const dimensions = ['lighting', 'color', 'space', 'composition', 'style'].map(
    (code, i) => ({
      code,
      label: ['光影', '色彩', '空间', '构图', '风格'][i],
      observation: `${id}观察`,
      interpretation: `${id}解释`,
      confidence: 0.5,
      evidence: [],
    }),
  );
  return {
    id,
    summary: id,
    intent: '',
    dimensions,
    tags: [],
    features: [],
    warnings: [],
    completionStatus: 'complete',
    provenance: { mode: 'real', profileVersion: '1', pipelineVersion: '1' },
    humanRevision: {
      revision: done ? 5 : 0,
      dimensions: dimensions.map((d) => ({
        ...d,
        review_status: done ? 'accept' : 'unreviewed',
        feedback_id: done ? 'f' : null,
      })),
    },
  };
}

function queue(): ReviewQueue {
  return {
    items: [1, 2, 3].map((i) => ({
      id: String(i),
      name: `image_00${i}`,
      result: result(String(i)),
    })),
    currentId: '1',
    dimension: 'color',
  };
}

it('retries a semantic failure with an existing partial result and removes only the local item', async () => {
  const state = queue();
  state.items[0].result!.provenance.semantic = { status: 'failed' };
  state.items[0].result!.assetId = 'existing-asset';
  state.items[0].asset = {
    id: 'file',
    file: new File(['x'], 'x.png', { type: 'image/png' }),
    previewUrl: 'data:image/png;base64,eA==',
    width: 1,
    height: 1,
  };
  mocks.read.mockResolvedValue(state);
  mocks.get.mockImplementation(
    async (id: string) => state.items.find((i) => i.id === id)!.result,
  );
  mocks.retry.mockResolvedValue(result('retry'));
  render(<AestheticWorkspace />);
  fireEvent.click(await screen.findByRole('button', { name: '重试当前图片' }));
  await waitFor(() =>
    expect(mocks.retry).toHaveBeenCalledWith(
      'existing-asset',
      expect.any(Function),
      true,
    ),
  );
  expect(mocks.analyze).not.toHaveBeenCalled();
  await waitFor(() =>
    expect(
      screen.queryByRole('button', { name: '重试当前图片' }),
    ).not.toBeInTheDocument(),
  );
  fireEvent.click(screen.getByRole('button', { name: '删除当前图片' }));
  fireEvent.click(await screen.findByRole('button', { name: '确认移除' }));
  await waitFor(() =>
    expect(
      screen.queryByRole('button', { name: 'image_001 review_pending' }),
    ).not.toBeInTheDocument(),
  );
  expect(
    screen.getByRole('button', { name: 'image_002 review_pending' }),
  ).toHaveAttribute('aria-current', 'true');
  await waitFor(() =>
    expect(mocks.write).toHaveBeenLastCalledWith(
      expect.objectContaining({
        items: expect.arrayContaining([expect.objectContaining({ id: '2' })]),
        currentId: '2',
      }),
    ),
  );
  expect(mocks.save).not.toHaveBeenCalled();
});

beforeEach(() => {
  vi.clearAllMocks();
  mocks.read.mockResolvedValue(emptyQueue);
  mocks.write.mockResolvedValue(undefined);
  mocks.get.mockImplementation(async (id: string) => result(id));
  vi.stubGlobal(
    'Image',
    class {
      naturalWidth = 100;
      naturalHeight = 100;
      onload?: () => void;
      set src(_value: string) {
        queueMicrotask(() => this.onload?.());
      }
    },
  );
});

it('reviews B while A is awaiting semantics and advances to ready C without losing either result', async () => {
  const state = queue();
  state.items[0].result = undefined;
  state.items[0].asset = {
    id: 'a',
    file: new File(['x'], 'a.png', { type: 'image/png' }),
    previewUrl: 'data:image/png;base64,eA==',
    width: 1,
    height: 1,
  };
  mocks.read.mockResolvedValue(state);
  let finish!: (value: AnalysisResult) => void;
  mocks.analyze.mockImplementation((_asset, onProgress) => {
    onProgress({
      assetId: 'asset-a',
      jobId: 'job-a',
      feature_analysis_status: 'completed',
      semantic_analysis_status: 'processing',
    });
    return new Promise<AnalysisResult>((resolve) => {
      finish = resolve;
    });
  });
  mocks.save.mockResolvedValue(result('2', true));
  render(<AestheticWorkspace />);
  await waitFor(() =>
    expect(
      screen.getByRole('button', { name: '分析未完成图片' }),
    ).not.toBeDisabled(),
  );
  fireEvent.click(screen.getByRole('button', { name: '分析未完成图片' }));
  await screen.findByRole('button', { name: 'image_001 semantic_processing' });
  const second = screen.getByRole('button', {
    name: 'image_002 review_pending',
  });
  expect(second).not.toBeDisabled();
  fireEvent.click(second);
  expect(screen.getByRole('button', { name: '确认' })).not.toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: '确认' }));
  await screen.findByRole('button', { name: 'image_002 completed' });
  expect(
    screen.getByRole('button', { name: 'image_003 review_pending' }),
  ).toHaveAttribute('aria-current', 'true');
  await act(async () => {
    finish(result('1'));
  });
  expect(
    screen.getByRole('button', { name: 'image_001 review_pending' }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole('button', { name: 'image_002 completed' }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole('button', { name: 'image_003 review_pending' }),
  ).toHaveAttribute('aria-current', 'true');
});

it('shows separated failure phases and blocks review of unsuccessful semantics', async () => {
  const state = queue();
  state.items[0].result!.feature_analysis_status = 'completed';
  state.items[0].result!.semantic_analysis_status = 'failed';
  state.items[0].result!.semantic_error_message = 'MODEL_HTTP_429';
  mocks.read.mockResolvedValue(state);
  mocks.get.mockImplementation(
    async (id: string) => state.items.find((i) => i.id === id)!.result,
  );
  render(<AestheticWorkspace />);
  const failed = await screen.findByRole('button', {
    name: 'image_001 failed',
  });
  expect(within(failed).getByText('✓ 特征完成')).toBeInTheDocument();
  expect(within(failed).getByText('⚠️ 语义分析失败')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '确认' })).toBeDisabled();
  expect(screen.getByRole('alert')).toHaveTextContent('MODEL_HTTP_429');
});

it('hides only requested navigation and accepts single/multiple files in order', async () => {
  render(<AestheticWorkspace />);
  const nav = screen.getByRole('navigation', { name: '主要功能' });
  expect(within(nav).getAllByRole('link')).toHaveLength(4);
  expect(within(nav).getByRole('link', { name: '视觉知识库' })).toHaveAttribute(
    'href',
    '/knowledge',
  );
  expect(within(nav).queryByText('视频镜头')).not.toBeInTheDocument();
  expect(within(nav).queryByText('模型评测')).not.toBeInTheDocument();
  const input = screen.getByLabelText('上传图片');
  await waitFor(() => expect(input).not.toBeDisabled());
  expect(input).toHaveAttribute('multiple');
  fireEvent.change(input, {
    target: { files: [new File(['one'], 'one.png', { type: 'image/png' })] },
  });
  await screen.findByRole('button', { name: 'image_001 pending' });
  await waitFor(() => expect(input).not.toBeDisabled());
  fireEvent.change(input, {
    target: {
      files: [
        new File(['two'], 'two.png', { type: 'image/png' }),
        new File(['three'], 'three.png', { type: 'image/png' }),
      ],
    },
  });
  await screen.findByRole('button', { name: 'image_003 pending' });
  mocks.analyze
    .mockResolvedValueOnce(result('one'))
    .mockRejectedValueOnce(new Error('failed'))
    .mockResolvedValueOnce(result('three'));
  await waitFor(() =>
    expect(
      screen.getByRole('button', { name: '分析未完成图片' }),
    ).not.toBeDisabled(),
  );
  fireEvent.click(screen.getByRole('button', { name: '分析未完成图片' }));
  await screen.findByRole('button', { name: 'image_003 review_pending' });
  expect(mocks.analyze.mock.calls.map((call) => call[0].file.name)).toEqual([
    'one.png',
    'two.png',
    'three.png',
  ]);
  expect(
    screen.getByRole('button', { name: 'image_002 failed' }),
  ).toBeInTheDocument();
});

it('advances across all dimensions before moving to the next image and restores position', async () => {
  let persisted = queue();
  mocks.read.mockImplementation(async () => persisted);
  mocks.write.mockImplementation(async (value: ReviewQueue) => {
    persisted = value;
  });
  mocks.save.mockImplementation(async (id: string) => {
    const updated = result(id);
    updated.humanRevision!.revision = 1;
    updated.humanRevision!.dimensions[1].review_status = 'accept';
    return updated;
  });
  const first = render(<AestheticWorkspace />);
  await screen.findByRole('button', { name: '确认' });
  expect(screen.getByRole('tab', { name: '色彩' })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  fireEvent.click(screen.getByRole('button', { name: '确认' }));
  await waitFor(() =>
    expect(screen.getByRole('tab', { name: '空间' })).toHaveAttribute(
      'aria-selected',
      'true',
    ),
  );
  expect(mocks.save).toHaveBeenCalledWith(
    '1',
    expect.objectContaining({
      feedback_type: 'accept',
      target_path: '/dimensions/color',
    }),
  );
  await waitFor(() => {
    expect(persisted.currentId).toBe('1');
    expect(persisted.dimension).toBe('space');
  });
  first.unmount();
  mocks.get.mockImplementation(
    async (id: string) =>
      persisted.items.find((i) => i.result?.id === id)!.result,
  );
  render(<AestheticWorkspace />);
  await waitFor(() =>
    expect(
      screen.getByRole('button', { name: 'image_001 reviewing' }),
    ).toHaveAttribute('aria-current', 'true'),
  );
  expect(screen.getByRole('tab', { name: '空间' })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  fireEvent.click(screen.getByRole('button', { name: '上一张' }));
  expect(screen.getByRole('tab', { name: '色彩 ✓' })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '下一张' }));
  fireEvent.click(
    screen.getByRole('button', { name: 'image_003 review_pending' }),
  );
  expect(screen.getByText('图片 3 / 3 · 已完成 0 / 3')).toBeInTheDocument();
});

it('keeps selection and completion unchanged on save failure', async () => {
  mocks.read.mockResolvedValue(queue());
  mocks.save.mockRejectedValue(new Error('REVISION_CONFLICT'));
  render(<AestheticWorkspace />);
  fireEvent.click(await screen.findByRole('button', { name: '确认' }));
  await screen.findByRole('alert');
  expect(
    screen.getByRole('button', { name: 'image_001 reviewing' }),
  ).toHaveAttribute('aria-current', 'true');
  expect(
    screen.queryByRole('button', { name: '拒绝' }),
  ).not.toBeInTheDocument();
});

it('restores completed state and skips completed, pending and failed candidates', async () => {
  const state = queue();
  state.items[0].result = result('1', true);
  mocks.read.mockResolvedValue(state);
  mocks.get.mockImplementation(
    async (id: string) => state.items.find((i) => i.id === id)!.result,
  );
  render(<AestheticWorkspace />);
  await screen.findByRole('button', { name: 'image_001 completed' });
  expect(reviewStatus(state.items[0])).toBe('completed');
  state.items[1].error = 'offline';
  expect(nextReview(state)).toEqual({ currentId: '3', dimension: 'lighting' });
  state.items[2].result = undefined;
  expect(nextReview(state)).toEqual({ currentId: '1', dimension: 'color' });
});

it('keeps the current image until all five dimensions are reviewed', () => {
  const state = queue();
  state.items[0].result!.humanRevision!.dimensions[1].review_status = 'accept';
  expect(nextReview(state)).toEqual({ currentId: '1', dimension: 'space' });

  for (const dimension of state.items[0].result!.humanRevision!.dimensions) {
    dimension.review_status = 'accept';
  }
  expect(nextReview(state)).toEqual({ currentId: '2', dimension: 'lighting' });
});
