import { expect, it, vi } from 'vitest';
import { searchCases } from './knowledge-api';
import { API_BASE_URL } from './api-analysis-provider';

it('uses existing search URLs, preserves conditions and resolves preview URLs', async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ items: [{ result_id: 'r', preview_url: '/api/v1/assets/a/content' }] }) });
  vi.stubGlobal('fetch', fetchMock);
  try {
    const body = { tags: ['cinematic'], numeric_filters: [] };
    const items = await searchCases('structured', body);
    expect(fetchMock).toHaveBeenCalledWith(`${API_BASE_URL}/search/structured`, expect.objectContaining({ method: 'POST', body: JSON.stringify(body) }));
    expect(items[0].preview_url).toBe(new URL('/api/v1/assets/a/content', API_BASE_URL).href);
    fetchMock.mockResolvedValueOnce({ ok: false, json: async () => ({ detail: 'SEMANTIC_SEARCH_NOT_CONFIGURED' }) });
    await expect(searchCases('semantic', { query: 'test', limit: 10 })).rejects.toThrow('SEMANTIC_SEARCH_NOT_CONFIGURED');
  } finally { vi.unstubAllGlobals(); }
});
