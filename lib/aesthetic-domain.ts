export type AnalysisStage =
  | 'idle'
  | 'ready'
  | 'extracting'
  | 'analyzing'
  | 'building'
  | 'complete';

export interface FeatureResult {
  extractor_code: string;
  extractor_version: string;
  feature_schema_version: string;
  method: string;
  standard: string | null;
  status: 'succeeded' | 'failed';
  parameters: Record<string, unknown>;
  values: Record<string, unknown>;
  artifacts: Array<Record<string, unknown>>;
  provenance: Record<string, unknown>;
  warnings: string[];
  error_detail: string | null;
}

export interface UploadedAsset {
  id: string;
  file: File;
  previewUrl: string;
  width: number;
  height: number;
}

export interface AnalysisDimension {
  code: string;
  label: string;
  observation: string;
  interpretation: string;
  confidence: number;
  evidence: string[];
}

export interface AnalysisResult {
  id: string;
  assetId?: string;
  jobId?: string;
  feature_analysis_status?: PhaseStatus;
  semantic_analysis_status?: PhaseStatus;
  semantic_error_message?: string | null;
  summary: string;
  intent: string;
  dimensions: AnalysisDimension[];
  tags: string[];
  provenance: {
    mode: 'mock' | 'hybrid' | 'real';
    profileVersion: string;
    pipelineVersion: string;
    semantic?: { status?: string; uncertainty?: Record<string, string> };
  };
  features: FeatureResult[];
  warnings: string[];
  completionStatus: 'complete' | 'partial';
  resolvedEvidence?: ResolvedEvidence[];
  humanRevision?: HumanRevision;
  feedbackHistory?: FeedbackEntry[];
  previewUrl?: string;
}

export type PhaseStatus = 'pending' | 'processing' | 'completed' | 'failed';
export interface AnalysisProgress {
  assetId: string;
  jobId: string;
  feature_analysis_status: PhaseStatus;
  semantic_analysis_status: PhaseStatus;
}

export interface FeedbackEntry {
  id: string;
  result_id: string;
  revision: number;
  feedback_type: 'accept' | 'edit' | 'reject' | 'flag_error';
  created_at: string;
  target_path: string | null;
  original_value: unknown;
  corrected_value: unknown;
  error_category: string | null;
  comment: string | null;
  base_revision: number | null;
}

export interface ResolvedEvidence {
  id: string;
  label: string;
  value: unknown;
  status: 'resolved' | 'invalid' | 'mock';
  supports_dimensions: string[];
}

export interface HumanRevision {
  revision: number;
  dimensions: Array<{
    code: string;
    label: string;
    observation: string;
    interpretation: string;
    review_status: 'unreviewed' | 'accept' | 'edit' | 'reject' | 'flag_error';
    feedback_id: string | null;
  }>;
}

export interface DimensionFeedback {
  feedback_type: 'accept' | 'edit' | 'reject';
  target_path: string;
  corrected_value?: { observation: string; interpretation: string };
  comment: string | null;
  error_category: string | null;
  base_revision: number;
}

export interface FeedbackDraft {
  verdict: 'accepted' | 'edited' | 'flagged' | null;
  note: string;
}

export interface AnalysisProvider {
  analyze(asset: UploadedAsset): Promise<AnalysisResult>;
}
