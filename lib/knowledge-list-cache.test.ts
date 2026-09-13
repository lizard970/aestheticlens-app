import { beforeEach, expect, it, vi } from 'vitest';
import { loadKnowledgePage, type KnowledgeCase, type KnowledgePageData } from './knowledge-api';
import { knowledgeListCache } from './knowledge-list-cache';

vi.mock('./knowledge-api', () => ({ loadKnowledgePage: vi.fn() }));
const item = { result_id: 'r', original_filename: 'one.png', preview_url: '/thumbnail' } as KnowledgeCase;
beforeEach(() => { knowledgeListCache.reset(); vi.clearAllMocks(); });

it('deduplicates in-flight loads and retains pages/cursor after a failed continuation', async () => {
  let resolve!: (page: KnowledgePageData) => void;
  vi.mocked(loadKnowledgePage).mockReturnValueOnce(new Promise(done => { resolve = done; }));
  const first = knowledgeListCache.load();
  expect(knowledgeListCache.load()).toBe(first);
  resolve({ items: [item], next_cursor: 'next' });
  await first;
  vi.mocked(loadKnowledgePage).mockRejectedValueOnce(new Error('offline'));
  await knowledgeListCache.load();
  expect(knowledgeListCache.getSnapshot().items).toEqual([item]);
  expect(knowledgeListCache.getSnapshot().next_cursor).toBe('next');
  vi.mocked(loadKnowledgePage).mockResolvedValueOnce({ items: [{ ...item, result_id: 'r2' }], next_cursor: null });
  await knowledgeListCache.load();
  expect(knowledgeListCache.getSnapshot().items).toHaveLength(2);
});

it('discards late responses after filter changes and does not resurrect deleted cases', async () => {
  let resolve!: (page: KnowledgePageData) => void;
  vi.mocked(loadKnowledgePage).mockReturnValueOnce(new Promise(done => { resolve = done; }));
  const first = knowledgeListCache.load();
  vi.mocked(loadKnowledgePage).mockResolvedValueOnce({ items: [item], next_cursor: null });
  await knowledgeListCache.load(true, { tag: 'new', query: '', review_status: '' });
  knowledgeListCache.remove('r');
  resolve({ items: [item], next_cursor: 'stale' });
  await first;
  expect(knowledgeListCache.getSnapshot().items).toEqual([]);
  expect(knowledgeListCache.getSnapshot().filters.tag).toBe('new');
  expect(knowledgeListCache.getSnapshot().next_cursor).toBeNull();
});
