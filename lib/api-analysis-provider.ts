import type { AnalysisProvider, AnalysisResult, DimensionFeedback, FeatureResult, FeedbackEntry, HumanRevision, ResolvedEvidence, UploadedAsset } from './aesthetic-domain';

export const API_BASE_URL = process.env.NEXT_PUBLIC_AESTHETICLENS_API_URL ?? 'http://localhost:8000/api/v1';

interface ApiResult {
  id: string;
  summary: string;
  dimensions: Array<{ code: string; label: string; observation: string; interpretation: string; confidence: number; evidence_refs: string[] }>;
  tags: string[];
  provenance: { mode?: 'mock' | 'hybrid' | 'real'; profile_version?: string; pipeline_version?: string; semantic?: AnalysisResult['provenance']['semantic'] };
  features?: FeatureResult[];
  warnings?: string[];
  completion_status?: 'complete' | 'partial';
  evidence?: ResolvedEvidence[];
  human_revision?: HumanRevision;
  feedback_history?: FeedbackEntry[];
  preview_url?: string;
}

export async function jsonRequest<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText })) as { detail?: string };
    throw new Error(payload.detail ?? `HTTP_${response.status}`);
  }
  return response.json() as Promise<T>;
}

export class ApiAnalysisProvider implements AnalysisProvider {
  async analyze(asset: UploadedAsset): Promise<AnalysisResult> {
    const form = new FormData();
    form.append('file', asset.file);
    const uploaded = await jsonRequest<{ id: string }>(`${API_BASE_URL}/assets`, { method: 'POST', body: form });
    const job = await jsonRequest<{ id: string; status: string }>(`${API_BASE_URL}/analysis-jobs`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID() },
      body: JSON.stringify({ target: { type: 'asset', id: uploaded.id }, analysis_profile_id: 'aesthetic-core-v1', requested_outputs: ['features', 'aesthetic_analysis', 'evidence'] }),
    });
    const result = await jsonRequest<ApiResult>(`${API_BASE_URL}/analysis-jobs/${job.id}/result`);
    return this.mapResult(result);
  }

  async getResult(id: string, revision?: number): Promise<AnalysisResult> {
    return this.mapResult(await jsonRequest<ApiResult>(`${API_BASE_URL}/analysis-results/${encodeURIComponent(id)}${revision === undefined ? '' : `?revision=${revision}`}`));
  }

  async history(): Promise<Array<{ id: string; original_filename: string; created_at: string }>> {
    return (await jsonRequest<{ items: Array<{ id: string; original_filename: string; created_at: string }> }>(`${API_BASE_URL}/analysis-results`)).items;
  }

  async saveFeedback(id: string, feedback: DimensionFeedback): Promise<AnalysisResult> {
    await jsonRequest(`${API_BASE_URL}/analysis-results/${encodeURIComponent(id)}/feedback`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(feedback),
    });
    return this.getResult(id);
  }

  private mapResult(result: ApiResult): AnalysisResult {
    return {
      id: result.id, summary: result.summary, intent: '计算特征提供画面事实；语义分析状态与不确定性见下方。',
      dimensions: result.dimensions.map((item) => ({ ...item, evidence: item.evidence_refs })), tags: result.tags,
      provenance: { mode: result.provenance.mode ?? 'mock', profileVersion: result.provenance.profile_version ?? 'unknown', pipelineVersion: result.provenance.pipeline_version ?? 'unknown', semantic: result.provenance.semantic },
      features: result.features ?? [], warnings: result.warnings ?? [], completionStatus: result.completion_status ?? 'complete',
      resolvedEvidence: result.evidence ?? [], humanRevision: result.human_revision,
      feedbackHistory: result.feedback_history ?? [],
      previewUrl: result.preview_url ? new URL(result.preview_url, API_BASE_URL).href : undefined,
    };
  }
}
