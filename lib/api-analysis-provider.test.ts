import { afterEach, expect, it, vi } from 'vitest';
import { ApiAnalysisProvider } from './api-analysis-provider';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

it('retries using the same server asset and polls existing job progress without uploading again', async () => {
  vi.useFakeTimers();
  let finish!: (value: unknown) => void;
  const fetchMock = vi
    .fn()
    .mockImplementation(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST')
        return new Promise((resolve) => {
          finish = resolve;
        });
      if (url.endsWith('/result'))
        return {
          ok: true,
          json: async () => ({
            id: 'result',
            asset_id: 'same-asset',
            job_id: 'job',
            dimensions: [],
            tags: [],
            summary: '',
            provenance: {
              feature_analysis_status: 'completed',
              semantic_analysis_status: 'completed',
            },
          }),
        };
      return {
        ok: true,
        json: async () => ({ progress_stage: 'analyzing', status: 'running' }),
      };
    });
  vi.stubGlobal('fetch', fetchMock);
  const progress = vi.fn();
  const running = new ApiAnalysisProvider().analyzeExisting(
    'same-asset',
    progress,
  );
  await vi.advanceTimersByTimeAsync(500);
  expect(progress).toHaveBeenLastCalledWith(
    expect.objectContaining({
      feature_analysis_status: 'completed',
      semantic_analysis_status: 'processing',
    }),
  );
  expect(JSON.parse(fetchMock.mock.calls[0][1].body).target.id).toBe(
    'same-asset',
  );
  const key = fetchMock.mock.calls[0][1].headers['Idempotency-Key'];
  expect(fetchMock.mock.calls[1][0]).toContain(`/analysis-jobs/${key}`);
  finish({ ok: true, json: async () => ({ id: key }) });
  const result = await running;
  expect(result.semantic_analysis_status).toBe('completed');
  expect(fetchMock.mock.calls.some((call) => call[0].endsWith('/assets'))).toBe(
    false,
  );
  const count = fetchMock.mock.calls.length;
  await vi.advanceTimersByTimeAsync(1000);
  expect(fetchMock).toHaveBeenCalledTimes(count);
});

it('recovers result and revision from GET, and saves via POST followed by server read', async () => {
  const payload = {
    id: 'result-id',
    summary: '原文',
    dimensions: [],
    tags: [],
    provenance: { mode: 'real' },
    evidence: [
      {
        id: 'feature:x#/mean',
        label: 'metric',
        value: 0.5,
        status: 'resolved',
        supports_dimensions: [],
      },
    ],
    human_revision: { revision: 2, dimensions: [] },
    feedback_history: [],
    preview_url: '/api/v1/assets/asset-id/content',
  };
  const fetch = vi
    .fn()
    .mockResolvedValue({ ok: true, json: async () => payload });
  vi.stubGlobal('fetch', fetch);
  const provider = new ApiAnalysisProvider();
  const recovered = await provider.getResult('result-id', 1);
  expect(fetch.mock.calls[0][0]).toContain(
    '/analysis-results/result-id?revision=1',
  );
  expect(recovered.resolvedEvidence?.[0].value).toBe(0.5);
  expect(recovered.humanRevision?.revision).toBe(2);
  expect(recovered.previewUrl).toContain('/api/v1/assets/asset-id/content');
  await provider.saveFeedback('result-id', {
    feedback_type: 'accept',
    target_path: '/dimensions/color',
    comment: null,
    error_category: null,
    base_revision: 2,
  });
  expect(fetch.mock.calls[1][1].method).toBe('POST');
  expect(fetch.mock.calls[2][0]).toContain('/analysis-results/result-id');
});
