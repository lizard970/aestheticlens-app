import type { FeatureResult } from '@/lib/aesthetic-domain';
import {
  formatFeatureNumber,
  formatFeatureValue,
} from '@/lib/feature-value-format';

type Props = {
  features: FeatureResult[];
  completionStatus: 'complete' | 'partial';
  resultWarnings: string[];
};
type Metric = {
  label: string;
  value: unknown;
  what: string;
  use: string;
  example: string;
};
const numericText = (value: unknown, path = '') =>
  typeof value === 'number' ? formatFeatureNumber(value, path) : '—';
const percentText = (value: unknown) =>
  typeof value === 'number' ? `${(value * 100).toFixed(1)}%` : '—';
const detailText = (value: unknown, path = '') =>
  formatFeatureValue(value, path);

function MetricCard({ metric }: { metric: Metric }) {
  return (
    <article className="rounded-lg border border-white/8 bg-black/15 p-3">
      <p className="text-xs text-muted-foreground">{metric.label}</p>
      <p className="mt-1 font-mono text-xl text-cyan-100">
        {numericText(metric.value)}
      </p>
      <div className="mt-3 space-y-1 text-xs leading-5 text-muted-foreground">
        <p>
          <span className="text-foreground">是什么：</span>
          {metric.what}
        </p>
        <p>
          <span className="text-foreground">有什么用：</span>
          {metric.use}
        </p>
        <p>
          <span className="text-foreground">例子：</span>
          {metric.example}
        </p>
      </div>
    </article>
  );
}

export function ComputationalFeatures({
  features,
  completionStatus,
  resultWarnings,
}: Props) {
  if (features.length === 0)
    return (
      <section
        role="alert"
        className="mb-5 rounded-xl border border-red-400/25 bg-red-400/8 p-4 text-sm text-red-100"
      >
        <p className="font-medium">真实特征结果缺失</p>
        <p className="mt-1 text-xs">
          API 返回了空
          features，当前结果不能视为完整成功，请重新运行或检查后端连接。
        </p>
      </section>
    );
  const byCode = new Map(
    features.map((feature) => [feature.extractor_code, feature]),
  );
  const tonal = byCode.get('tonal_occupancy');
  const lightness = byCode.get('cie_lightness');
  const global = byCode.get('global_tonal_contrast');
  const local = byCode.get('multiscale_local_contrast');
  const scales = Array.isArray(local?.values.scales)
    ? (local.values.scales as Array<Record<string, unknown>>)
    : [];
  const warnings = [
    ...new Set([
      ...resultWarnings,
      ...features.flatMap((feature) => feature.warnings),
    ]),
  ];
  const failed = features.filter((feature) => feature.status === 'failed');
  const metrics: Metric[] = [
    {
      label: '平均感知明度 L*',
      value: lightness?.values.mean,
      what: '全画面 CIELAB L* 的算术平均。',
      use: '快速比较两张画面的整体感知明度中心。',
      example: '纯黑约为 0，纯白约为 100，中灰约为 53.6。',
    },
    {
      label: '典型感知明度 L*（median）',
      value: lightness?.values.median,
      what: '将全部像素排序后位于中间的 L*。',
      use: '减少极少数极亮或极暗像素对中心值的影响。',
      example: '一小盏灯不会像平均值那样明显拉高 median。',
    },
    {
      label: '全局色调跨度 p95-p05',
      value: global?.values.lstar_p95_p05_span,
      what: '常用亮调 P95 与常用暗调 P05 的 L* 距离。',
      use: '描述画面主体影调覆盖范围，同时避开少量端点噪声。',
      example: '全灰画面接近 0，黑白各半画面接近 100。',
    },
    {
      label: '明度 IQR',
      value: global?.values.lstar_iqr,
      what: '中间 50% 像素的 L* 范围，即 P75−P25。',
      use: '观察主要像素是否集中在窄影调区间。',
      example: '雾景通常比黑白图拥有更窄的 IQR。',
    },
    {
      label: '明度标准差',
      value: global?.values.lstar_standard_deviation,
      what: '所有 L* 相对平均值的总体离散程度。',
      use: '补充反映全局明度变化强弱，但不判断美感。',
      example: '均匀灰为 0，明暗混合画面通常更高。',
    },
  ];
  return (
    <section
      className="mb-5 rounded-xl border border-cyan-300/20 bg-cyan-300/5 p-4"
      aria-label="真实计算"
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-cyan-100">真实计算</p>
          <p className="mt-1 text-xs text-muted-foreground">
            确定性像素统计，不是审美评分或曝光诊断
          </p>
        </div>
        <span
          className={`rounded-full px-2.5 py-1 font-mono text-xs ${completionStatus === 'partial' ? 'bg-amber-300/15 text-amber-100' : 'bg-cyan-300/15 text-cyan-100'}`}
        >
          当前结果状态：{completionStatus}
        </span>
      </div>
      {(failed.length > 0 || warnings.length > 0) && (
        <div className="mb-4 rounded-lg border border-amber-300/20 bg-amber-300/7 p-3 text-xs leading-5 text-amber-100">
          {failed.map((item) => (
            <p key={item.extractor_code}>
              提取失败 · {item.extractor_code}：{item.error_detail}
            </p>
          ))}
          {warnings.map((warning) => (
            <p key={warning}>色彩配置警告：{warning}</p>
          ))}
        </div>
      )}
      {tonal?.status === 'succeeded' ? (
        <article className="mb-3 rounded-lg border border-white/8 bg-black/15 p-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <p className="text-sm font-medium">Tone distribution · 明暗层级</p>
            <p className="font-mono text-[10px] text-muted-foreground">
              配置 v{detailText(tonal.values.configuration_version)}
            </p>
          </div>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            按可配置 CIELAB L*
            区间统计；这是检索与比较用的操作性分区，不代表语义阴影、正确曝光或美学质量。
          </p>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            {[
              {
                key: 'shadow_share',
                label: `暗部占比（L* ≤ ${detailText(tonal.values.shadow_lstar_max)}）`,
                what: '落入当前低明度区间的像素比例。',
                use: '比较画面低明度区域的面积结构。',
                example: '纯黑测试图应接近 100%。',
                color: 'bg-slate-400',
              },
              {
                key: 'midtone_share',
                label: '中间调占比',
                what: '位于暗部与高光边界之间的像素比例。',
                use: '观察画面是否主要由中间明度层级承载。',
                example: '均匀中灰测试图应接近 100%。',
                color: 'bg-cyan-300',
              },
              {
                key: 'highlight_share',
                label: `高光占比（L* ≥ ${detailText(tonal.values.highlight_lstar_min)}）`,
                what: '落入当前高明度区间的像素比例。',
                use: '比较画面高明度区域的面积结构。',
                example: '纯白测试图应接近 100%。',
                color: 'bg-amber-200',
              },
            ].map((zone) => (
              <div
                key={zone.key}
                className="rounded-lg border border-white/6 p-3"
              >
                <div className="flex items-end justify-between gap-2">
                  <p className="text-xs text-muted-foreground">{zone.label}</p>
                  <p className="font-mono text-lg text-foreground">
                    {percentText(tonal.values[zone.key])}
                  </p>
                </div>
                <div className="mt-2 h-2 overflow-hidden rounded-full bg-white/8">
                  <div
                    className={`h-full rounded-full ${zone.color}`}
                    style={{ width: percentText(tonal.values[zone.key]) }}
                  />
                </div>
                <div className="mt-3 space-y-1 text-[11px] leading-5 text-muted-foreground">
                  <p>
                    <span className="text-foreground">是什么：</span>
                    {zone.what}
                  </p>
                  <p>
                    <span className="text-foreground">有什么用：</span>
                    {zone.use}
                  </p>
                  <p>
                    <span className="text-foreground">例子：</span>
                    {zone.example}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </article>
      ) : (
        <div
          role="alert"
          className="mb-3 rounded-lg border border-red-400/20 bg-red-400/8 p-3 text-xs text-red-100"
        >
          影调层级结果缺失或提取失败，不能静默生成暗部/高光占比。
        </div>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        {metrics.map((metric) => (
          <MetricCard key={metric.label} metric={metric} />
        ))}
      </div>
      <article className="mt-3 rounded-lg border border-white/8 bg-black/15 p-3">
        <p className="text-sm font-medium">多尺度局部对比</p>
        <div className="mt-3 space-y-3">
          {scales.map((scale) => {
            const energy =
              typeof scale.energy_rms === 'number' ? scale.energy_rms : 0;
            return (
              <div key={String(scale.scale_fraction)}>
                <div className="mb-1 flex justify-between font-mono text-xs">
                  <span>
                    尺度 {numericText(scale.scale_fraction, 'scale_fraction')}
                  </span>
                  <span>RMS {numericText(energy, 'energy_rms')}</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-white/8">
                  <div
                    className="h-full rounded-full bg-cyan-300"
                    style={{
                      width: `${Math.min(100, Math.max(1, energy * 100))}%`,
                    }}
                  />
                </div>
              </div>
            );
          })}
        </div>
        <div className="mt-3 space-y-1 text-xs leading-5 text-muted-foreground">
          <p>
            <span className="text-foreground">是什么：</span>
            不同图像相对尺度上的明暗邻域变化。
          </p>
          <p>
            <span className="text-foreground">有什么用：</span>
            区分相同直方图但空间结构不同的画面。
          </p>
          <p>
            <span className="text-foreground">例子：</span>
            黑白二分图是一条大分界，棋盘格则有许多细小分界。
          </p>
        </div>
      </article>
      <details className="mt-4 rounded-lg border border-white/8 p-3">
        <summary className="cursor-pointer text-sm text-cyan-100">
          查看技术详情
        </summary>
        <div className="mt-3 space-y-3 text-[11px] leading-5 text-muted-foreground">
          {features.map((feature) => (
            <div
              key={feature.extractor_code}
              className="border-t border-white/6 pt-2"
            >
              <p className="font-mono text-foreground">
                {feature.extractor_code} · {feature.status} · extractor{' '}
                {feature.extractor_version} · schema{' '}
                {feature.feature_schema_version}
              </p>
              <p>
                方法：{feature.method}
                {feature.standard ? ` · ${feature.standard}` : ''}
              </p>
              <p>分位数/数值：{detailText(feature.values)}</p>
              <p>参数：{detailText(feature.parameters)}</p>
              <p>ICC / provenance：{detailText(feature.provenance)}</p>
            </div>
          ))}
        </div>
      </details>
    </section>
  );
}
