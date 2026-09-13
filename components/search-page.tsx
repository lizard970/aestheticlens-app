'use client';
/* eslint-disable @next/next/no-img-element -- Existing API preview URLs. */
import { useRef, useState } from 'react';
import Link from 'next/link';
import { searchCases, type KnowledgeCase } from '@/lib/knowledge-api';
import { WorkspacePage } from './workspace-navigation';
import { CompareButton } from './case-compare';
import { Button } from './ui/button';
import { Input } from './ui/input';

const pageSize = 12;
export function SearchPage() {
  const [query, setQuery] = useState('');
  const [tags, setTags] = useState('');
  const [field, setField] = useState('');
  const [op, setOp] = useState('gte');
  const [value, setValue] = useState('');
  const [threshold, setThreshold] = useState('0.3');
  const [items, setItems] = useState<KnowledgeCase[]>([]);
  const [visible, setVisible] = useState(pageSize);
  const [debug, setDebug] = useState<Record<string, unknown>>({});
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const request = useRef(0);
  async function run() {
    const version = ++request.current;
    setLoading(true);
    setError('');
    setItems([]);
    setDebug({});
    setVisible(pageSize);
    setSearched(true);
    try {
      if (
        (field || value) &&
        (!field.trim() || !value.trim() || !Number.isFinite(Number(value)))
      )
        throw new Error('请填写完整的数值条件');
      if (
        !threshold.trim() ||
        !Number.isFinite(Number(threshold)) ||
        Number(threshold) < -1 ||
        Number(threshold) > 1
      )
        throw new Error('相似度门槛须在 -1 到 1 之间');
      const data = await searchCases(
        'hybrid',
        {
          query: query.trim() || null,
          tags: tags
            .split(/[,，]/)
            .map((t) => t.trim())
            .filter(Boolean),
          numeric_filters: field.trim()
            ? [{ field: field.trim(), op, value: Number(value) }]
            : [],
          limit: 50,
          min_similarity: Number(threshold),
        },
        (filters) => {
          if (version === request.current) setDebug(filters);
        },
      );
      if (version === request.current) setItems(data);
    } catch (reason) {
      if (version === request.current)
        setError(reason instanceof Error ? reason.message : '检索失败');
    } finally {
      if (version === request.current) setLoading(false);
    }
  }
  return (
    <WorkspacePage active="/search">
      <h1 className="text-2xl font-semibold">对比与检索</h1>
      <p className="text-sm text-muted-foreground">
        描述想找的画面，检索已确认知识案例。最多返回 50 项，不用弱匹配补足数量。
      </p>
      <form
        className="space-y-3"
        onSubmit={(event) => {
          event.preventDefault();
          void run();
        }}
      >
        <div className="flex gap-3">
          <Input
            aria-label="查询"
            placeholder="例如：电影感的小猫"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            maxLength={2000}
          />
          <Button type="submit" disabled={loading}>
            检索
          </Button>
        </div>
        <details>
          <summary className="cursor-pointer">高级筛选</summary>
          <div className="mt-3 flex flex-wrap items-end gap-3">
            <label htmlFor="search-tags">
              标签（逗号分隔）
              <Input
                id="search-tags"
                value={tags}
                onChange={(e) => setTags(e.target.value)}
              />
            </label>
            <label htmlFor="search-field">
              数值字段
              <Input
                id="search-field"
                value={field}
                onChange={(e) => setField(e.target.value)}
                placeholder="shadow_occupancy"
              />
            </label>
            <label htmlFor="search-op">
              运算符
              <select
                id="search-op"
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
            <label htmlFor="search-threshold">
              相似度门槛
              <Input
                id="search-threshold"
                type="number"
                min="-1"
                max="1"
                step="0.01"
                value={threshold}
                onChange={(e) => setThreshold(e.target.value)}
              />
            </label>
          </div>
          <p className="text-xs text-muted-foreground">
            所有筛选条件同时满足；相似度门槛仅用于有描述文本的排序，不是正确率。
          </p>
        </details>
      </form>
      {loading && <output>正在检索…</output>}
      {error && (
        <p role="alert">检索失败：{error}。请检查条件或服务配置后重试。</p>
      )}
      {!searched && <p>输入描述或设置筛选后开始检索。</p>}
      {searched && !loading && !error && (
        <>
          <p>
            {items.length
              ? `找到 ${items.length} 个案例`
              : '暂无满足条件和相关性门槛的案例。'}
          </p>
          <details>
            <summary>检索调试信息</summary>
            <pre className="whitespace-pre-wrap text-xs">
              {JSON.stringify(debug, null, 2)}
            </pre>
          </details>
        </>
      )}
      <div className="columns-1 gap-4 sm:columns-2 xl:columns-3">
        {items.slice(0, visible).map((item) => (
          <article
            key={item.result_id}
            className="mb-4 break-inside-avoid rounded-xl border border-white/10 p-4"
          >
            <Link href={`/knowledge/${item.result_id}`}>
              <img
                src={item.preview_url}
                alt={`${item.original_filename} 缩略图`}
                loading="lazy"
                className="mb-3 h-auto w-full rounded-lg"
              />
            </Link>
            <CompareButton item={item} />
            <Link
              href={`/knowledge/${item.result_id}`}
              className="ml-2 underline"
            >
              {item.original_filename}
            </Link>
            <p>{item.preview_text}</p>
            <p>标签：{item.tags.join(' · ') || '暂无'}</p>
            {item.similarity != null && (
              <p>相似度：{item.similarity.toFixed(3)}（非正确率）</p>
            )}
            {item.matched_structured_conditions && (
              <details>
                <summary>已应用条件</summary>
                <p className="break-words text-xs">
                  {JSON.stringify(item.matched_structured_conditions)}
                </p>
              </details>
            )}
          </article>
        ))}
      </div>
      {visible < items.length && (
        <Button
          variant="outline"
          onClick={() => setVisible((count) => count + pageSize)}
        >
          加载更多
        </Button>
      )}
    </WorkspacePage>
  );
}
