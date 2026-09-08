export type AnalysisStage = 'idle' | 'ready' | 'extracting' | 'analyzing' | 'building' | 'complete';

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
}

export interface FeedbackDraft {
  verdict: 'accepted' | 'edited' | 'flagged' | null;
  note: string;
}

export interface AnalysisProvider {
  analyze(asset: UploadedAsset): Promise<AnalysisResult>;
}
