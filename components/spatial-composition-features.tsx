import type { FeatureResult } from '@/lib/aesthetic-domain';

type Props = {
  features: FeatureResult[];
};

const asRecord = (value: unknown): Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};

const numberText = (value: unknown, digits = 3) =>
  typeof value === 'number' ? value.toFixed(digits) : '—';

const percentText = (value: unknown) =>
  typeof value === 'number' ? `${(value * 100).toFixed(1)}%` : '—';

const hintLabels: Record<string, string> = {
  center_sharper_than_surround: '中心区域比周边更清晰',
  surround_sharper_than_center: '周边区域比中心更清晰',
  vertical_focus_gradient_detected: '检测到纵向清晰度梯度',
  undetermined: '无法可靠判断',
  upper_left: '左上',
  upper_center: '上方居中',
  upper_right: '右上',
  middle_left: '左侧居中',
  middle_center: '画面中央',
  middle_right: '右侧居中',
  lower_left: '左下',
  lower_center: '下方居中',
  lower_right: '右下',
};

function Metric({
  label,
  value,
  description,
}: {
  label: string;
  value: string;
  description: string;
}) {
  return (
    <article className="rounded-lg border border-white/8 bg-black/15 p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 font-mono text-xl text-cyan-100">{value}</p>
      <p className="mt-2 text-xs leading-5 text-muted-foreground">
        {description}
      </p>
    </article>
  );
}

function MissingFeature({
  name,
  feature,
}: {
  name: string;
  feature?: FeatureResult;
}) {
  if (feature?.status === 'succeeded') return null;

  return (
    <p
      role="alert"
      className="rounded-lg border border-red-400/20 bg-red-400/8 p-3 text-sm text-red-200"
    >
      {name}真实计算不可用
      {feature?.error_detail
        ? `：${feature.error_detail}`
        : '：API 未返回对应特征'}
    </p>
  );
}

export function SpaceComputationalFeatures({ features }: Props) {
  const feature = features.find(
    (item) => item.extractor_code === 'space_structure',
  );
  const complexity = asRecord(feature?.values.spatial_complexity);
  const foreground = asRecord(feature?.values.foreground_background_hint);
  const depth = asRecord(feature?.values.depth_layer_hint);
  const bands = asRecord(depth.band_focus_signal);
  const depthHint =
    typeof depth.hint === 'string' ? depth.hint : 'undetermined';
  const foregroundHint =
    typeof foreground.hint === 'string' ? foreground.hint : 'undetermined';

  return (
    <section
      aria-label="空间真实计算"
      className="mb-5 rounded-xl border border-cyan-300/20 bg-cyan-300/5 p-4"
    >
      <div className="mb-4">
        <p className="text-sm font-semibold text-cyan-100">真实计算 · 空间</p>
        <p className="mt-1 text-xs text-muted-foreground">
          只描述边缘、纹理与清晰度线索，不把二维线索伪装成真实三维深度。
        </p>
      </div>

      <MissingFeature name="空间" feature={feature} />
      {feature?.status === 'succeeded' && (
        <div className="grid gap-3 sm:grid-cols-2">
          <Metric
            label="空间复杂度"
            value={numberText(complexity.score)}
            description={`边缘密度 ${percentText(complexity.edge_density)}，结合纹理变化形成 0–1 指数；细密街景通常高于纯色墙面。`}
          />
          <Metric
            label="留白比例（低信息区域）"
            value={percentText(feature.values.empty_space_ratio)}
            description="边缘和局部纹理都较少的区域占比；例如干净天空通常会增加这一比例。"
          />
          <Metric
            label="景深线索"
            value={hintLabels[depthHint] ?? depthHint}
            description={`上/中/下清晰度信号：${numberText(bands.top)} / ${numberText(bands.middle)} / ${numberText(bands.bottom)}。差异不足时明确显示无法判断。`}
          />
          <Metric
            label="前后景倾向"
            value={hintLabels[foregroundHint] ?? foregroundHint}
            description="比较中心与周边的清晰度分离，只给出焦点区域倾向，不识别具体前景或背景物体。"
          />
        </div>
      )}
    </section>
  );
}

export function CompositionComputationalFeatures({ features }: Props) {
  const feature = features.find(
    (item) => item.extractor_code === 'composition_geometry',
  );
  const subject = asRecord(feature?.values.subject_position_hint);
  const center = asRecord(feature?.values.visual_center_offset);
  const symmetry = asRecord(feature?.values.symmetry_score);
  const thirds = asRecord(feature?.values.rule_of_thirds_score);
  const subjectHint =
    typeof subject.hint === 'string' ? subject.hint : 'undetermined';

  return (
    <section
      aria-label="构图真实计算"
      className="mb-5 rounded-xl border border-cyan-300/20 bg-cyan-300/5 p-4"
    >
      <div className="mb-4">
        <p className="text-sm font-semibold text-cyan-100">真实计算 · 构图</p>
        <p className="mt-1 text-xs text-muted-foreground">
          基于显著区域代理与几何关系，不输出情绪、电影感或美丑判断。
        </p>
      </div>

      <MissingFeature name="构图" feature={feature} />
      {feature?.status === 'succeeded' && (
        <div className="grid gap-3 sm:grid-cols-2">
          <Metric
            label="主体位置提示"
            value={hintLabels[subjectHint] ?? subjectHint}
            description="用边缘与纹理形成的主视觉区域估计位置；纯色图没有可靠显著区域时会显示无法判断。"
          />
          <Metric
            label="视觉中心偏移"
            value={numberText(center.normalized_distance)}
            description="主视觉中心到画面中心的归一化距离；0 表示重合，越大表示偏离越远。"
          />
          <Metric
            label="留白"
            value={percentText(feature.values.negative_space_ratio)}
            description="构图语境下的低信息区域占比；例如主体旁的大块纯净背景会提高它。"
          />
          <Metric
            label="对称性"
            value={numberText(symmetry.mean)}
            description={`左右 ${numberText(symmetry.left_right)}，上下 ${numberText(symmetry.top_bottom)}；1 表示镜像结构非常接近。`}
          />
          <Metric
            label="三分法接近度"
            value={numberText(thirds.score)}
            description="主视觉中心靠近四个三分线交点时得分更高；这是几何接近度，不代表构图一定更好。"
          />
        </div>
      )}
    </section>
  );
}
