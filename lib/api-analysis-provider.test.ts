import { afterEach, expect, it, vi } from 'vitest';
import { ApiAnalysisProvider } from './api-analysis-provider';

afterEach(() => vi.unstubAllGlobals());

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
    base_revision: 2,
  });
  expect(fetch.mock.calls[1][1].method).toBe('POST');
  expect(fetch.mock.calls[2][0]).toContain('/analysis-results/result-id');
});
