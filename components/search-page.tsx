'use client';
import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { searchCases, type KnowledgeCase } from '@/lib/knowledge-api';
import { WorkspacePage } from './workspace-navigation';
import { Button } from './ui/button';
import { Input } from './ui/input';

export function SearchPage() {
  const [mode, setMode] = useState<'structured' | 'semantic' | 'hybrid'>(
    'structured',
  );
  const [query, setQuery] = useState('');
  const [tags, setTags] = useState('');
  const [field, setField] = useState('');
  const [op, setOp] = useState('gte');
  const [value, setValue] = useState('');
  const [items, setItems] = useState<KnowledgeCase[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const request = useRef(0);
  async function run(initial = false) {
    const version = ++request.current;
    setLoading(true);
    setError('');
    setItems([]);
    setSelected([]);
    try {
      const selectedMode = initial ? 'structured' : mode;
      const filterTags = initial
        ? []
        : tags
            .split(/[,，]/)
            .map((t) => t.trim())
            .filter(Boolean);
      if (!initial && selectedMode === 'semantic' && !query.trim())
        throw new Error('请输入语义查询');
      if (
        !initial &&
        selectedMode !== 'semantic' &&
        (field || value) &&
        (!field.trim() || !value.trim() || !Number.isFinite(Number(value)))
      )
        throw new Error('请填写完整的数值条件');
      const numeric =
        !initial && field.trim()
          ? [
              {
                [selectedMode === 'structured' ? 'feature_ref' : 'field']:
                  field.trim(),
                op,
                value: Number(value),
              },
            ]
          : [];
      const body =
        selectedMode === 'semantic'
          ? { query: query.trim(), limit: 20 }
          : selectedMode === 'hybrid'
            ? {
                query: query.trim() || null,
                tags: filterTags,
                numeric_filters: numeric,
                limit: 20,
              }
            : { tags: filterTags, numeric_filters: numeric };
      const data = await searchCases(selectedMode, body);
      if (version === request.current) setItems(data);
    } catch (reason) {
      if (version === request.current)
        setError(reason instanceof Error ? reason.message : '检索失败');
    } finally {
      if (version === request.current) setLoading(false);
    }
  }
  useEffect(() => {
    let active = true;
    void searchCases('structured', { tags: [], numeric_filters: [] }).then(data => { if (active) setItems(data); })
      .catch(reason => { if (active) setError(reason instanceof Error ? reason.message : '加载失败'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  return (
    <WorkspacePage active="/search">
      <h1 className="text-2xl font-semibold">对比与检索</h1>
      <p className="text-sm text-muted-foreground">
        检索已确认知识案例；选择两项并列比较已有摘要。结构化条件采用
        AND，混合检索先过滤再按语义相似度排序。
      </p>
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          void run();
        }}
      >
        <label>
          检索方式
          <select
            aria-label="检索方式"
            className="block rounded border bg-background p-2"
            value={mode}
            onChange={(e) => setMode(e.target.value as typeof mode)}
          >
            <option value="structured">结构化</option>
            <option value="semantic">语义</option>
            <option value="hybrid">混合</option>
          </select>
        </label>
        {mode !== 'structured' && (
          <label htmlFor="search-query">
            查询
            <Input
              id="search-query"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              maxLength={2000}
            />
          </label>
        )}
        {mode !== 'semantic' && (
          <>
            <label htmlFor="search-tags">
              标签（逗号分隔）
              <Input id="search-tags" value={tags} onChange={(e) => setTags(e.target.value)} />
            </label>
            <label htmlFor="search-field">
              数值字段
              <Input
                id="search-field"
                value={field}
                onChange={(e) => setField(e.target.value)}
                placeholder={
                  mode === 'structured'
                    ? 'feature:tonal_occupancy#/shadow_share'
                    : 'shadow_occupancy'
                }
              />
            </label>
            <label>
              运算符
              <select
                className="block rounded border bg-background p-2"
                value={op}
                onChange={(e) => setOp(e.target.value)}
              >
                {['eq', 'gt', 'gte', 'lt', 'lte'].map((o) => (
                  <option key={o}>{o}</option>
                ))}
              </select>
            </label>
            <label htmlFor="search-value">
              数值
              <Input
                id="search-value"
                type="number"
                step="any"
                value={value}
                onChange={(e) => setValue(e.target.value)}
              />
            </label>
          </>
        )}
        <Button type="submit" disabled={loading}>
          检索
        </Button>
      </form>
      {loading && <output>正在检索…</output>}
      {error && (
        <p role="alert">检索失败：{error}。请检查条件或服务配置后重试。</p>
      )}
      {!loading && !error && <p>找到 {items.length} 个案例</p>}
      <div className="space-y-3">
        {items.map((item) => (
          <article
            key={item.result_id}
            className="rounded-xl border border-white/10 p-4"
          >
            <label className="mr-3">
              <input
                type="checkbox"
                checked={selected.includes(item.result_id)}
                disabled={
                  selected.length === 2 && !selected.includes(item.result_id)
                }
                onChange={(e) =>
                  setSelected((current) =>
                    e.target.checked
                      ? [...current, item.result_id]
                      : current.filter((id) => id !== item.result_id),
                  )
                }
              />{' '}
              选择对比
            </label>
            <Link href={`/knowledge/${item.result_id}`} className="underline">
              {item.original_filename}
            </Link>
            <p>{item.preview_text}</p>
            <p>标签：{item.tags.join(' · ') || '暂无'}</p>
            {item.similarity != null && (
              <p>余弦相似度：{item.similarity.toFixed(3)}（非正确率）</p>
            )}
            {item.matched_structured_conditions && (
              <p>
                匹配条件：{JSON.stringify(item.matched_structured_conditions)}
              </p>
            )}
          </article>
        ))}
      </div>
      {selected.length > 0 && (
        <section aria-label="案例对比" className="grid gap-3 md:grid-cols-2">
          {items
            .filter((item) => selected.includes(item.result_id))
            .map((item) => (
              <article
                key={item.result_id}
                className="rounded-xl border border-amber-300/20 p-4"
              >
                <h2>{item.original_filename}</h2>
                <p>{item.preview_text}</p>
                <p>{item.tags.join(' · ')}</p>
                <Link
                  href={`/knowledge/${item.result_id}`}
                  className="underline"
                >
                  查看五维与人工审核详情
                </Link>
              </article>
            ))}
        </section>
      )}
    </WorkspacePage>
  );
}
