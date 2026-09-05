import { DEFAULT_ANALYSIS_PROFILE } from './analysis-profile';
import type { AnalysisProvider, AnalysisResult, UploadedAsset } from './aesthetic-domain';

const delay = (milliseconds: number) => new Promise((resolve) => setTimeout(resolve, milliseconds));

export class MockAnalysisProvider implements AnalysisProvider {
  async analyze(asset: UploadedAsset): Promise<AnalysisResult> {
    await delay(500);
    const orientation = asset.width >= asset.height ? '横向画幅' : '纵向画幅';

    return {
      id: crypto.randomUUID(),
      summary: `${orientation}已进入结构化分析流程，五个美学维度与证据引用均已建立。`,
      intent: '验证上传、任务状态、结果展示和人工反馈的产品闭环。',
      dimensions: DEFAULT_ANALYSIS_PROFILE.dimensions.map((dimension, index) => ({
        code: dimension.code,
        label: dimension.label,
        observation: dimension.mockObservation,
        interpretation: dimension.mockInterpretation,
        confidence: 0.64 + index * 0.04,
        evidence: [...dimension.evidence],
      })),
      tags: [orientation, '交互原型', '待真实模型分析'],
      provenance: { mode: 'mock', profileVersion: DEFAULT_ANALYSIS_PROFILE.version, pipelineVersion: DEFAULT_ANALYSIS_PROFILE.pipelineVersion },
    };
  }
}
