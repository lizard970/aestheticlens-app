'use client';
/* eslint-disable @next/next/no-img-element -- Existing API image previews. */
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import type { AnalysisResult } from '@/lib/aesthetic-domain';
import type { KnowledgeCase } from '@/lib/knowledge-api';
import { ApiAnalysisProvider } from '@/lib/api-analysis-provider';
import { Button } from './ui/button';

const Context = createContext<{
  items: KnowledgeCase[];
  toggle: (item: KnowledgeCase) => void;
}>({ items: [], toggle: () => {} });
const storageKey = 'aestheticlens-compare-v1';
const dimensions = ['composition', 'color', 'lighting', 'space', 'style'];
// Existing comparable scalar metrics only; no derived scores.
const metrics = [
  ['tonal_occupancy', 'shadow_share'],
  ['tonal_occupancy', 'highlight_share'],
  ['global_tonal_contrast', 'lstar_standard_deviation'],
];

export function CompareButton({ item }: { item: KnowledgeCase }) {
  const { items, toggle } = useContext(Context);
  const selected = items.some((entry) => entry.result_id === item.result_id);
  return (
    <Button
      variant="outline"
      disabled={!selected && items.length >= 3}
      onClick={() => toggle(item)}
    >
      {selected ? '移出对比' : '加入对比'}
    </Button>
  );
}

export function CompareProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<KnowledgeCase[]>([]);
  const [results, setResults] = useState<Record<string, AnalysisResult>>({});
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const version = useRef(0);
  const invalidate = useCallback(() => { version.current++; }, []);
  useEffect(() => {
    try {
      const saved: unknown = JSON.parse(
        sessionStorage.getItem(storageKey) ?? '[]',
      );
      if (Array.isArray(saved))
        // eslint-disable-next-line react/react-compiler -- Restore browser-only storage after SSR hydration.
        setItems(
          saved
            .filter(
              (item): item is KnowledgeCase =>
                item &&
                typeof item.result_id === 'string' &&
                typeof item.preview_url === 'string' &&
                typeof item.original_filename === 'string',
            )
            .filter(
              (item, index, all) =>
                all.findIndex((other) => other.result_id === item.result_id) ===
                index,
            )
            .slice(0, 3),
        );
    } catch {
      /* Storage is optional; selection still works in memory. */
    }
    return invalidate;
  }, [invalidate]);
  function change(next: KnowledgeCase[]) {
    version.current++;
    setLoading(false);
    setOpen(false);
    setItems(next);
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(next));
    } catch {
      /* Optional browser storage. */
    }
  }
  async function start() {
    const request = ++version.current;
    setLoading(true);
    setError('');
    setOpen(true);
    setResults({});
    const provider = new ApiAnalysisProvider();
    const loaded = await Promise.all(
      items.map(async (item) => {
        try {
          return [
            item.result_id,
            await provider.getResult(item.result_id),
          ] as const;
        } catch {
          return null;
        }
      }),
    );
    if (request !== version.current) return;
    setResults(Object.fromEntries(loaded.filter((item) => item !== null)));
    setError(
      loaded.some((item) => item === null)
        ? '部分案例详情读取失败，请重新开始对比重试。'
        : '',
    );
    setLoading(false);
  }
  function value(id: string, field: string) {
    const result = results[id];
    if (!result) return '未加载';
    if (field === 'tags')
      return (
        result.humanRevision?.tags?.slice().sort().join(' · ') ??
        '暂无独立人工标签记录'
      );
    if (dimensions.includes(field))
      return (
        result.humanRevision?.dimensions.find((d) => d.code === field)
          ?.interpretation ?? '暂无人工审核记录'
      );
    const [extractor, key] = field.split('/');
    const metric = result.features.find(
      (f) => f.extractor_code === extractor && f.status === 'succeeded',
    )?.values[key];
    return typeof metric === 'number'
      ? key.endsWith('_share')
        ? `${(metric * 100).toFixed(1)}%`
        : metric.toFixed(2)
      : '无数据';
  }
  const fields = [
    'tags',
    ...dimensions,
    ...metrics
      .map((parts) => parts.join('/'))
      .filter((field) =>
        items.some((item) => value(item.result_id, field) !== '无数据'),
      ),
  ];
  return (
    <Context.Provider
      value={{
        items,
        toggle: (item) =>
          change(
            items.some((entry) => entry.result_id === item.result_id)
              ? items.filter((entry) => entry.result_id !== item.result_id)
              : items.length < 3
                ? [...items, item]
                : items,
          ),
      }}
    >
      {children}
      {items.length > 0 && (
        <aside
          aria-label="对比托盘"
          className="fixed bottom-3 right-3 z-30 flex max-w-[95vw] items-center gap-2 rounded-xl border bg-background p-3 shadow-lg"
        >
          <span>{items.length} / 3</span>
          {items.map((item) => (
            <div key={item.result_id}>
              <img
                src={item.preview_url}
                alt={item.original_filename}
                className="h-12 w-14 object-contain"
              />
              <button
                aria-label={`移除 ${item.original_filename}`}
                onClick={() =>
                  change(
                    items.filter((entry) => entry.result_id !== item.result_id),
                  )
                }
              >
                移除
              </button>
            </div>
          ))}
          <Button variant="outline" onClick={() => change([])}>
            清空
          </Button>
          <Button
            disabled={items.length < 2 || loading}
            onClick={() => void start()}
          >
            开始对比
          </Button>
        </aside>
      )}
      {open && (
        <section
          aria-label="案例对比"
          className="fixed inset-4 bottom-28 z-40 overflow-auto rounded-xl border bg-background p-4 shadow-lg"
        >
          <Button
            onClick={() => {
              version.current++;
              setLoading(false);
              setOpen(false);
            }}
          >
            关闭对比
          </Button>
          <p className="my-2 text-sm text-muted-foreground">
            仅高亮不同字段；展示已有人工版本与计算指标，不生成新分析。
          </p>
          {loading && <p>读取所选案例…</p>}
          {error && <p role="alert">{error}</p>}
          <table className="w-full table-fixed text-sm">
            <thead>
              <tr>
                {items.map((item) => (
                  <th key={item.result_id} className="p-3">
                    <img
                      src={item.preview_url}
                      alt={`${item.original_filename} 对比原图`}
                      className="h-52 w-full object-contain"
                    />
                    {item.original_filename}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {!loading &&
                fields.map((field) => (
                  <tr key={field}>
                    {items.map((item) => (
                      <td
                        key={item.result_id}
                        className={`border p-3 align-top break-words ${new Set(items.map((entry) => value(entry.result_id, field))).size > 1 ? 'bg-amber-300/10' : ''}`}
                      >
                        <p className="mb-1 text-muted-foreground">
                          {field === 'tags' ? '人工确认标签' : field}
                        </p>
                        {value(item.result_id, field) || '无标签'}
                      </td>
                    ))}
                  </tr>
                ))}
            </tbody>
          </table>
        </section>
      )}
    </Context.Provider>
  );
}
