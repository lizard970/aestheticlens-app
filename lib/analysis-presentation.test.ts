import { describe, expect, it } from 'vitest';
import type { AnalysisResult } from './aesthetic-domain';
import { analysisPresentation } from './analysis-presentation';

describe('analysis provenance presentation', () => {
  const result = (mode: 'mock' | 'hybrid' | 'real', status?: string) =>
    ({
      provenance: {
        mode,
        pipelineVersion: 'fixture-version',
        semantic: status ? { status } : undefined,
      },
    }) as AnalysisResult;

  it('uses actual modes and versions without assuming Hybrid', () => {
    expect(analysisPresentation(null).pipeline).toBe('等待分析');
    for (const mode of ['mock', 'hybrid', 'real'] as const) {
      expect(analysisPresentation(result(mode)).pipeline.toLowerCase()).toBe(
        `${mode} pipeline · fixture-version`,
      );
    }
  });

  it('distinguishes real failure, real success and old Mock results', () => {
    expect(analysisPresentation(result('real', 'failed')).semantics).toContain(
      '模型调用失败',
    );
    expect(
      analysisPresentation(result('real', 'succeeded')).confidence,
    ).toContain('未校准');
    expect(analysisPresentation(result('hybrid')).semantics).toContain('Mock');
  });
});
