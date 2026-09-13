'use client';
/* eslint-disable @next/next/no-img-element -- Existing backend serves original image previews. */
import { useEffect, useState, useSyncExternalStore } from 'react';
import Link from 'next/link';
import { DeleteKnowledgeCase } from './delete-knowledge-case';
import { CompareButton } from './case-compare';
import { WorkspacePage } from './workspace-navigation';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { caseStatus } from '@/lib/knowledge-api';
import { knowledgeListCache } from '@/lib/knowledge-list-cache';
import { DeferredKnowledgeCard } from './deferred-knowledge-card';
import type { AnalysisResult } from '@/lib/aesthetic-domain';

export function KnowledgeEvidence({
  result,
  full = false,
}: {
  result?: AnalysisResult;
  full?: boolean;
}) {
  if (!result) return <p>暂无人工审核记录（详情未加载）</p>;
  return (
    <div className="space-y-3 text-sm">
      <p>AI 建议标签：{result.tags.join(' · ') || '暂无'}</p>
      <p>
        人工确认标签：
        {result.humanRevision?.tags != null
          ? result.humanRevision.tags.join(' · ') || '无风格标签'
          : '当前接口未提供独立的逐标签审核字段。'}
      </p>
      <p>人工审核状态：{caseStatus(result)}</p>
      <dl className="space-y-3">
        {['composition', 'color', 'lighting', 'space', 'style'].map((code) => {
          const ai = result.dimensions.find((d) => d.code === code);
          const human = result.humanRevision?.dimensions.find(
            (d) => d.code === code,
          );
          return (
            <div key={code} className="rounded-lg border border-white/10 p-3">
              <dt className="font-medium">
                {ai?.label ?? code} · {code}
              </dt>
              <dd className="mt-1 leading-6">
                AI 分析：{ai?.interpretation ?? '无数据'}
              </dd>
              <dd className="leading-6">
                人工校准：
                {human?.feedback_id ? human.interpretation : '暂无人工审核记录'}
              </dd>
              {full && (
                <dd className="leading-6">
                  AI 观察：{ai?.observation ?? '无数据'}
                  <br />
                  人工观察：
                  {human?.feedback_id ? human.observation : '暂无人工审核记录'}
                </dd>
              )}
            </div>
          );
        })}
      </dl>
      <details open={full}>
        <summary className="cursor-pointer">
          修改与反馈记录（{result.feedbackHistory?.length ?? 0}）
        </summary>
        {!result.feedbackHistory?.length && <p>暂无人工审核记录</p>}
        {result.feedbackHistory?.map((f) => (
          <article
            key={f.id}
            className="mt-2 rounded border border-white/10 p-2"
          >
            <p>
              {f.feedback_type} · {f.target_path} · {f.created_at}
            </p>
            <p>原值：{JSON.stringify(f.original_value)}</p>
            <p>修正值：{JSON.stringify(f.corrected_value)}</p>
            {f.error_category && <p>错误类别：{f.error_category}</p>}
            {f.comment && <p>备注：{f.comment}</p>}
          </article>
        ))}
      </details>
    </div>
  );
}

export function KnowledgePage() {
  const snapshot = useSyncExternalStore(
    knowledgeListCache.subscribe,
    knowledgeListCache.getSnapshot,
    knowledgeListCache.getServerSnapshot,
  );
  const [tag, setTag] = useState(snapshot.filters.tag);
  const [status, setStatus] = useState(snapshot.filters.review_status);
  const [query, setQuery] = useState(snapshot.filters.query);
  useEffect(() => {
    if (!knowledgeListCache.getSnapshot().loaded)
      void knowledgeListCache.load();
    const savedScroll = knowledgeListCache.getScroll();
    const frame = requestAnimationFrame(() => window.scrollTo(0, savedScroll));
    const saveScroll = () => knowledgeListCache.saveScroll(window.scrollY);
    window.addEventListener('scroll', saveScroll, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('scroll', saveScroll);
    };
  }, []);
  const tags = [...new Set(snapshot.items.flatMap((item) => item.tags))].sort();
  const times = snapshot.items
    .map((item) => Date.parse(item.updated_at ?? ''))
    .filter(Number.isFinite);
  return (
    <WorkspacePage active="/knowledge">
      <h1 className="text-2xl font-semibold">视觉知识库</h1>
      <p className="text-sm text-muted-foreground">
        AI 提出分析 → 人工校准 →
        形成知识资产。仅展示已确认、真实且证据有效的案例。
      </p>
      <div className="flex flex-wrap gap-6 rounded-xl border border-white/10 p-4">
        <p>
          已加载案例：{snapshot.items.length}
          {snapshot.next_cursor ? '（还有更多）' : ''}
        </p>
        <p>已加载案例确认标签：{tags.length}</p>
        <p>
          最近更新时间（已加载）：
          {times.length
            ? new Date(Math.max(...times)).toLocaleString()
            : '暂无时间数据'}
        </p>
      </div>
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          void knowledgeListCache.load(true, {
            tag,
            review_status: status,
            query,
          });
        }}
      >
        <Input
          aria-label="搜索案例"
          placeholder="搜索案例、文件名或分析内容"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className="max-w-sm"
        />
        <label htmlFor="knowledge-tag">
          标签
          <Input
            id="knowledge-tag"
            aria-label="按标签筛选"
            list="knowledge-tags"
            value={tag}
            onChange={(event) => setTag(event.target.value)}
          />
        </label>
        <datalist id="knowledge-tags">
          {tags.map((value) => (
            <option key={value} value={value}>{value}</option>
          ))}
        </datalist>
        <label htmlFor="knowledge-status">
          审核状态
          <select
            id="knowledge-status"
            aria-label="按审核状态筛选"
            className="rounded border bg-background p-2"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            <option value="">全部</option>
            {[
              '已确认',
              '已人工修改',
              '审核中',
              '需重新审核',
              '暂无人工审核记录',
            ].map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <Button type="submit" disabled={snapshot.loading}>
          筛选
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={snapshot.loading}
          onClick={() => void knowledgeListCache.load(true)}
        >
          刷新
        </Button>
      </form>
      {snapshot.error && (
        <p role="alert">读取失败：{snapshot.error}。已加载内容保留，请重试。</p>
      )}
      {snapshot.loading && <output>正在读取知识资产…</output>}
      {!snapshot.loading &&
        !snapshot.error &&
        snapshot.loaded &&
        !snapshot.items.length && (
          <p>暂无符合条件的知识案例。完成真实分析的五维审核后再刷新。</p>
        )}
      <div className="columns-1 gap-4 md:columns-2 xl:columns-3">
        {snapshot.items.map((entry) => (
          <DeferredKnowledgeCard key={entry.result_id} id={entry.result_id}>
            <article className="rounded-xl border border-white/10 bg-card p-4">
              <Link
                aria-label={'预览 ' + entry.original_filename}
                href={'/knowledge/' + entry.result_id}
              >
                <img
                  src={entry.preview_url}
                  alt={entry.original_filename}
                  loading="lazy"
                  decoding="async"
                  className="mb-3 aspect-[4/3] w-full rounded-lg object-contain"
                />
              </Link>
              <Link
                className="block truncate font-semibold underline"
                href={'/knowledge/' + entry.result_id}
              >
                {entry.original_filename}
              </Link>
              <p className="break-all text-xs text-muted-foreground">
                asset_id：{entry.asset_id}
              </p>
              <p className="break-all text-xs text-muted-foreground">
                result_id：{entry.result_id}
              </p>
              <p className="mt-2 text-sm">
                {entry.review_status ?? '暂无人工审核记录'}
              </p>
              <p className="line-clamp-2 text-sm">
                人工确认标签：{entry.tags.join(' · ') || '无风格标签'}
              </p>
              <p className="my-2 line-clamp-3 text-sm">{entry.preview_text}</p>
              <p className="mb-2 text-xs text-muted-foreground">
                点击案例查看完整五维与审核历史
              </p>
              <div className="flex flex-wrap gap-2">
                <CompareButton item={entry} />
                <DeleteKnowledgeCase
                  id={entry.result_id}
                  name={entry.original_filename}
                  onDeleted={() => knowledgeListCache.remove(entry.result_id)}
                />
              </div>
            </article>
          </DeferredKnowledgeCard>
        ))}
      </div>
      {snapshot.next_cursor && (
        <Button
          variant="outline"
          disabled={snapshot.loading}
          onClick={() => void knowledgeListCache.load()}
        >
          加载更多（20 条）
        </Button>
      )}
    </WorkspacePage>
  );
}
