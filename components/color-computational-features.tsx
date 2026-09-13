import type { FeatureResult } from '@/lib/aesthetic-domain';

type Props = {
  features: FeatureResult[];
};

const numberText = (value: unknown, digits = 2) =>
  typeof value === 'number' ? value.toFixed(digits) : '—';

const percentText = (value: unknown) =>
  typeof value === 'number'
    ? `${(value * 100).toFixed(1)}%`
    : '—';


function Metric({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <article className="rounded-lg border border-white/8 bg-black/15 p-3">
      <p className="text-xs text-muted-foreground">
        {label}
      </p>

      <p className="mt-1 font-mono text-xl text-cyan-100">
        {value}
      </p>
    </article>
  );
}


export function ColorComputationalFeatures({
  features,
}: Props) {
  const byCode = new Map(
    features.map((feature) => [
      feature.extractor_code,
      feature,
    ]),
  );

  const chroma = byCode.get('cie_chroma');
  const occupancy = byCode.get('chromatic_occupancy');
  const hue = byCode.get('hue_distribution');
  const palette = byCode.get('dominant_palette');
  const accent = byCode.get('accent_palette');
  const warmCool = byCode.get('warm_cool_distribution');
  const contrast = byCode.get('palette_color_contrast');
  const colorfulness = byCode.get('image_colorfulness');

  const colors = Array.isArray(palette?.values.colors)
    ? (palette.values.colors as Array<Record<string, unknown>>)
    : [];
  const accents = accent?.status === 'succeeded' && Array.isArray(accent.values.colors)
    ? (accent.values.colors as Array<Record<string, unknown>>)
    : [];

  return (
    <section className="mb-5 rounded-xl border border-cyan-300/20 bg-cyan-300/5 p-4">
      <div className="mb-4">
        <p className="text-sm font-semibold text-cyan-100">
          真实色彩计算
        </p>

        <p className="mt-1 text-xs text-muted-foreground">
          确定性色彩统计，不包含审美评分
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <Metric
          label="平均彩度 C*ab"
          value={numberText(chroma?.values.mean)}
        />

        <Metric
          label="典型彩度 C*ab"
          value={numberText(chroma?.values.median)}
        />

        <Metric
          label="有彩色像素占比"
          value={percentText(
            occupancy?.values.chromatic_share,
          )}
        />

        <Metric
          label="有效色相数量"
          value={numberText(
            hue?.values.effective_hue_count,
          )}
        />

        <Metric
          label="暖色占有彩区域"
          value={percentText(
            warmCool?.values.warm_share_of_chromatic,
          )}
        />

        <Metric
          label="冷色占有彩区域"
          value={percentText(
            warmCool?.values.cool_share_of_chromatic,
          )}
        />

        <Metric
          label="整体 Colorfulness"
          value={numberText(
            colorfulness?.values.colorfulness,
          )}
        />

        <Metric
          label="主色最大 ΔE2000"
          value={numberText(
            contrast?.values.max_delta_e2000,
          )}
        />
      </div>

      {[{ title: '主色板 · 面积排序', colors, empty: '暂无主色数据' },
        { title: '强调色板 · 视觉强调排序', colors: accents, empty: !accent ? '此历史结果尚未提取强调色' : accent.status !== 'succeeded' ? '强调色提取未完成' : '未检出符合条件的小面积强调色' }].map(group => (
      <article key={group.title} aria-label={group.title} className="mt-4 rounded-lg border border-white/8 bg-black/15 p-3">
        <p className="text-sm font-medium">
          {group.title}
        </p>

        {group.colors.length === 0 ? (
          <p className="mt-3 text-xs text-muted-foreground">
            {group.empty}
          </p>
        ) : (
          <div className="mt-3 flex flex-wrap gap-3">
            {group.colors.map((color) => {
              const hex = typeof color.hex_srgb === 'string'
                ? color.hex_srgb
                : '#000000';

              return (
                <div
                  key={String(color.rank)}
                  className="w-24"
                >
                  <div
                    className="h-12 rounded-lg border border-white/10"
                    style={{
                      backgroundColor: hex,
                    }}
                  />

                  <p className="mt-1 font-mono text-xs">
                    {hex}
                  </p>

                  <p className="text-xs text-muted-foreground">
                    {percentText(color.share)}
                  </p>
                </div>
              );
            })}
          </div>
        )}
      </article>
      ))}
      <p className="mt-2 text-xs text-muted-foreground">占比均相对整张分析图；强调色可同时出现在主色板中，不重复累计面积。</p>
    </section>
  );
}
