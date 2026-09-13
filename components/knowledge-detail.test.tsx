import { render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { KnowledgeDetail } from './knowledge-detail';
import { ApiAnalysisProvider, API_BASE_URL } from '@/lib/api-analysis-provider';
import { knowledgeListCache } from '@/lib/knowledge-list-cache';

it('requests only the opened case and its asset metadata, never the entire result history', async () => {
  knowledgeListCache.reset();
  const detail = vi.spyOn(ApiAnalysisProvider.prototype, 'getResult').mockResolvedValue({
    id: 'r', assetId: 'a', summary: 'Detailed summary', intent: '', tags: [], dimensions: [], features: [], warnings: [], completionStatus: 'complete',
    provenance: { mode: 'real', profileVersion: '1', pipelineVersion: '1' },
  });
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ id: 'a', original_filename: 'detail.png' }) });
  vi.stubGlobal('fetch', fetchMock);
  try {
    render(<KnowledgeDetail id="r" />);
    await screen.findByText('Detailed summary');
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(detail).toHaveBeenCalledExactlyOnceWith('r');
    expect(fetchMock.mock.calls[0][0]).toBe(`${API_BASE_URL}/assets/a`);
    expect(screen.getByRole('link', { name: '返回视觉知识库' })).toHaveAttribute('href', '/knowledge');
  } finally { detail.mockRestore(); vi.unstubAllGlobals(); }
});
