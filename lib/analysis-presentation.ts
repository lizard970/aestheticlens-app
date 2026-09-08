import type { AnalysisResult } from './aesthetic-domain';

const modeNames = { mock: 'Mock', hybrid: 'Hybrid', real: 'Real' };

export function analysisPresentation(result: AnalysisResult | null) {
  if (!result)
    return {
      pipeline: '等待分析',
      semantics: '等待分析',
      confidence: '尚无判断',
    };
  const { mode, pipelineVersion, semantic } = result.provenance;
  const failed = semantic?.status === 'failed';
  const mock =
    semantic?.status === 'mock' || (semantic === undefined && mode !== 'real');
  return {
    pipeline: `${modeNames[mode]} Pipeline · ${pipelineVersion}`,
    semantics: failed
      ? '模型调用失败 · 计算结果已保留'
      : mock
        ? 'Mock 语义 · 交互占位'
        : '真实模型分析 · 请结合证据审阅',
    confidence: failed
      ? '未生成判断'
      : mock
        ? 'Mock 占位值'
        : '模型自报置信值 · 未校准，不代表正确概率',
  };
}
