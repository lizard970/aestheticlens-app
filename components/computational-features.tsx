import { Badge } from '@/components/ui/badge';
import type { FeatureResult } from '@/lib/aesthetic-domain';

const definitions: Record<string, { title: string; purpose: string; example: string; fields: Array<[string, string]> }> = {
  image_metadata: { title: '图像与标准化', purpose: '记录实际分析的尺寸、格式、色彩配置假设和透明度。', example: 'EXIF 旋转后的尺寸与原始文件尺寸会分别保留，便于复现。', fields: [['analysis_width', '分析宽度'], ['analysis_height', '分析高度'], ['profile_assumed', '是否假定 sRGB'], ['alpha_present', '是否含透明度']] },
  relative_luminance: { title: '线性相对亮度 Y', purpose: '表示物理意义上的相对光量分布，不是审美或曝光评分。', example: '同样是编码值 128 的灰色，线性 Y 约为 0.216，而不是 0.5。', fields: [['mean', '平均 Y'], ['median', '中位 Y'], ['p05', 'P05'], ['p95', 'P95']] },
  cie_lightness: { title: 'CIELAB L* 明度', purpose: '用更接近人眼感知间距的尺度描述明暗分布。', example: '标准黑约为 0，标准白约为 100，中灰约为 53.6。', fields: [['mean', '平均 L*'], ['median', '中位 L*'], ['p05', 'P05'], ['p95', 'P95']] },
  global_tonal_contrast: { title: '全局影调跨度', purpose: '描述常用暗调和亮调之间的总体距离，不判断画面好坏。', example: '两碗平均灰度相近的豆子，一碗全灰、另一碗黑白各半，后者跨度更大。', fields: [['lstar_p95_p05_span', 'P95−P05'], ['lstar_iqr', '四分位距'], ['lstar_standard_deviation', '标准差']] },
  multiscale_local_contrast: { title: '多尺度局部对比', purpose: '区分明暗结构出现在哪些空间尺度。', example: '黑白各半与棋盘格比例相同，但前者是一条大分界，后者有许多小分界。', fields: [] },
  source_endpoint_occupancy: { title: '源编码端点占用', purpose: '只统计源像素恰好为全黑或全白的比例。', example: '它不会把“接近黑色”任意定义成阴影区域。', fields: [['exact_black_occupancy', '精确黑占比'], ['exact_white_occupancy', '精确白占比']] },
};

const valueText = (value: unknown) => typeof value === 'number' ? value.toFixed(4) : typeof value === 'string' ? value : value == null ? '—' : JSON.stringify(value);

export function ComputationalFeatures({ features }: { features: FeatureResult[] }) {
  const visible = features.filter((item) => definitions[item.extractor_code]);
  const provenance = visible[0]?.provenance ?? {};
  const warnings = [...new Set(visible.flatMap((item) => item.warnings))];
  return <section className="mb-6 rounded-xl border border-cyan-300/15 bg-cyan-300/4 p-4">
    <div className="mb-4 flex items-center justify-between"><div><p className="text-xs font-medium text-cyan-200">真实计算 · Real computation</p><p className="mt-1 text-xs text-muted-foreground">可复现数值事实，不是审美评分或曝光诊断</p></div><Badge variant="outline">{visible.filter((item) => item.status === 'succeeded').length}/{visible.length} 成功</Badge></div>
    <div className="grid gap-3 sm:grid-cols-2">{visible.map((feature) => {
      const definition = definitions[feature.extractor_code];
      const scales = Array.isArray(feature.values.scales) ? feature.values.scales as Array<Record<string, unknown>> : [];
      return <article key={feature.extractor_code} className="rounded-lg bg-black/15 p-3"><div className="flex items-start justify-between gap-2"><h3 className="text-sm font-medium">{definition.title}</h3><span className="font-mono text-[10px] text-muted-foreground">v{feature.extractor_version}</span></div>
        {feature.status === 'failed' ? <p className="mt-2 text-xs text-red-200">提取失败：{feature.error_detail}</p> : <><dl className="mt-2 grid grid-cols-2 gap-2">{definition.fields.map(([key, label]) => <div key={key}><dt className="text-[11px] text-muted-foreground">{label}</dt><dd className="font-mono text-sm">{valueText(feature.values[key])}</dd></div>)}{scales.map((scale) => <div key={String(scale.scale_fraction)}><dt className="text-[11px] text-muted-foreground">尺度 {valueText(scale.scale_fraction)}</dt><dd className="font-mono text-sm">RMS {valueText(scale.energy_rms)}</dd></div>)}</dl></>}
        <p className="mt-3 text-xs leading-5 text-muted-foreground">{definition.purpose}</p><p className="mt-1 text-xs leading-5 text-muted-foreground">例：{definition.example}</p><p className="mt-2 truncate text-[10px] text-muted-foreground" title={feature.method}>{feature.method}{feature.standard ? ` · ${feature.standard}` : ''}</p>
      </article>;
    })}</div>
    <div className="mt-3 rounded-lg border border-white/8 p-3 text-[11px] leading-5 text-muted-foreground"><p>工作表示：{valueText(provenance.working_representation)}</p><p>参考白：{valueText(provenance.reference_white)} · 分析栅格：{valueText(provenance.analysis_raster_dimensions)}</p><p>配置来源：{valueText(provenance.profile_source)}</p>{warnings.length > 0 && <p className="mt-1 text-amber-200">警告：{warnings.join('；')}</p>}</div>
  </section>;
}
