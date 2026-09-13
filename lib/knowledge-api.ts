import {
  API_BASE_URL,
  jsonRequest,
} from './api-analysis-provider';
import type { AnalysisResult } from './aesthetic-domain';

export interface KnowledgeCase {
  asset_id: string;
  result_id: string;
  original_filename: string;
  preview_url: string;
  tags: string[];
  revision: number;
  preview_text: string;
  review_status?: string;
  updated_at?: string | null;
  similarity?: number | null;
  matched_structured_conditions?: {
    tags: string[];
    numeric_filters: Array<{ field: string; op: string; value: number }>;
  };
}
export interface CaseView {
  entry: KnowledgeCase;
  result?: AnalysisResult;
  error?: string;
}

export async function searchCases(
  mode: 'structured' | 'semantic' | 'hybrid',
  request: object,
  onDebug?: (filters: Record<string, unknown>) => void,
): Promise<KnowledgeCase[]> {
  const response = await jsonRequest<{ items: KnowledgeCase[]; applied_filters?: Record<string, unknown> }>(
    `${API_BASE_URL}/search/${mode}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    },
  );
  onDebug?.(response.applied_filters ?? {});
  return response.items.map((item) => ({
    ...item,
    preview_url: new URL(item.preview_url, API_BASE_URL).href,
  }));
}

export interface KnowledgeFilters { tag: string; review_status: string; query: string }
export interface KnowledgePageData { items: KnowledgeCase[]; next_cursor: string | null }
export async function loadKnowledgePage(filters: KnowledgeFilters, cursor: string | null = null): Promise<KnowledgePageData> {
  const params = new URLSearchParams({ ...filters });
  if (cursor) params.set('cursor', cursor);
  const data = await jsonRequest<KnowledgePageData>(`${API_BASE_URL}/knowledge/cases?${params}`);
  return { ...data, items: data.items.map(item => ({ ...item, preview_url: new URL(item.preview_url, API_BASE_URL).href })) };
}

export async function deleteKnowledgeCase(resultId: string) {
  const response = await fetch(`${API_BASE_URL}/knowledge/cases/${encodeURIComponent(resultId)}`, { method: 'DELETE' });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText })) as { detail?: string };
    throw new Error(payload.detail ?? `HTTP_${response.status}`);
  }
}

export function caseStatus(result?: AnalysisResult) {
  if (
    !result?.humanRevision ||
    !result.humanRevision.dimensions.some((d) => d.feedback_id)
  )
    return '暂无人工审核记录';
  if (
    result.humanRevision.dimensions.some(
      (d) => d.review_status === 'reject' || d.review_status === 'flag_error',
    )
  )
    return '需重新审核';
  if (
    result.humanRevision.dimensions.some(
      (d) => d.review_status === 'unreviewed',
    )
  )
    return '审核中';
  return result.humanRevision.dimensions.some((d) => d.review_status === 'edit')
    ? '已人工修改'
    : '已确认';
}

export function lastReview(result?: AnalysisResult) {
  const times = (result?.feedbackHistory ?? [])
    .map((f) => Date.parse(f.created_at))
    .filter(Number.isFinite);
  return times.length ? Math.max(...times) : null;
}
