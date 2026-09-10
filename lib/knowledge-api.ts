import {
  API_BASE_URL,
  ApiAnalysisProvider,
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
const provider = new ApiAnalysisProvider();

export async function searchCases(
  mode: 'structured' | 'semantic' | 'hybrid',
  request: object,
): Promise<KnowledgeCase[]> {
  const response = await jsonRequest<{ items: KnowledgeCase[] }>(
    `${API_BASE_URL}/search/${mode}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    },
  );
  return response.items.map((item) => ({
    ...item,
    preview_url: new URL(item.preview_url, API_BASE_URL).href,
  }));
}

export async function loadKnowledge(): Promise<CaseView[]> {
  const entries = await searchCases('structured', {
    tags: [],
    numeric_filters: [],
  });
  const cases: CaseView[] = [];
  // Bound concurrent detail requests while preserving server order.
  for (let start = 0; start < entries.length; start += 6) {
    cases.push(
      ...(await Promise.all(
        entries.slice(start, start + 6).map(async (entry) => {
          try {
            return { entry, result: await provider.getResult(entry.result_id) };
          } catch {
            return { entry, error: '详情读取失败，请刷新重试' };
          }
        }),
      )),
    );
  }
  return cases;
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
