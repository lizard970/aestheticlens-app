import type { AnalysisDimension } from './aesthetic-domain';

export interface DimensionDefinition {
  code: AnalysisDimension['code'];
  label: string;
  mockObservation: string;
  mockInterpretation: string;
  evidence: string[];
}

export const DEFAULT_ANALYSIS_PROFILE = {
  id: 'aesthetic-core-v1',
  name: '画面美学基础分析',
  version: '1.0.0',
  pipelineVersion: '0.1.0-mock',
  dimensions: [
    { code: 'composition', label: '构图', mockObservation: '已建立主体区域、画面边界与视觉重心的分析槽位。', mockInterpretation: '当前为交互 Mock；阶段 1C 将由视觉模型生成画面专属判断。', evidence: ['主体区域', '视觉重心'] },
    { code: 'color', label: '色彩', mockObservation: '已建立主色、冷暖关系与饱和度分布的分析槽位。', mockInterpretation: '阶段 1B 将先接入真实像素统计，再交给模型解释。', evidence: ['主色分布', '冷暖比例'] },
    { code: 'lighting', label: '光影', mockObservation: '已建立亮度、对比度、暗部与高光比例的分析槽位。', mockInterpretation: '计算事实和语义解释将分别记录，避免模型覆盖原始数据。', evidence: ['亮度分布', '明暗比例'] },
    { code: 'space', label: '空间', mockObservation: '已建立层次、景深线索和画面密度的分析槽位。', mockInterpretation: '静帧无法确认的运动信息会单独标记为不确定项。', evidence: ['层次线索', '边缘密度'] },
    { code: 'style', label: '风格', mockObservation: '已建立风格、情绪和表达意图的分析槽位。', mockInterpretation: '正式结果必须引用画面证据，不允许只输出泛化形容词。', evidence: ['视觉语义', '证据引用'] },
  ] satisfies DimensionDefinition[],
} as const;
