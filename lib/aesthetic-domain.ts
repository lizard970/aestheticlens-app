export type AnalysisStage = 'idle' | 'ready' | 'extracting' | 'analyzing' | 'building' | 'complete';

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
    mode: 'mock';
    profileVersion: string;
    pipelineVersion: string;
  };
}

export interface FeedbackDraft {
  verdict: 'accepted' | 'edited' | 'flagged' | null;
  note: string;
}

export interface AnalysisProvider {
  analyze(asset: UploadedAsset): Promise<AnalysisResult>;
}
