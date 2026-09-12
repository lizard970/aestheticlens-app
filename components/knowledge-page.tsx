'use client';
/* eslint-disable @next/next/no-img-element -- Existing backend serves original image previews. */
import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { DeleteKnowledgeCase } from './delete-knowledge-case';
import { WorkspacePage } from './workspace-navigation';
import { Button } from './ui/button';
import { Input } from './ui/input';
import {
  caseStatus,
  lastReview,
  loadKnowledge,
  type CaseView,
} from '@/lib/knowledge-api';
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
  const [cases, setCases] = useState<CaseView[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [tag, setTag] = useState('');
  const [status, setStatus] = useState('');
  const [query, setQuery] = useState('');
  const sequence = useRef(0);
  async function refresh() {
    const version = ++sequence.current;
    setLoading(true);
    setError('');
    try {
      const data = await loadKnowledge();
      if (version === sequence.current) setCases(data);
    } catch (reason) {
      if (version === sequence.current)
        setError(reason instanceof Error ? reason.message : '加载失败');
    } finally {
      if (version === sequence.current) setLoading(false);
    }
  }
  useEffect(() => {
    let active = true;
    void loadKnowledge().then(data => { if (active) setCases(data); })
      .catch(reason => { if (active) setError(reason instanceof Error ? reason.message : '加载失败'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  const tags = [...new Set(cases.flatMap((c) => c.entry.tags))].sort();
  const confirmedTags = new Set(
    cases.flatMap((c) => c.result?.humanRevision?.tags ?? []),
  );
  const hasTagRevisions = cases.some(
    (c) => c.result?.humanRevision?.tags != null,
  );
  const times = cases
    .map((c) => lastReview(c.result))
    .filter((n): n is number => n !== null);
  const filtered = cases.filter(
    (c) =>
      (!tag || c.entry.tags.includes(tag)) &&
      (!status || caseStatus(c.result) === status) &&
      `${c.entry.original_filename} ${c.entry.asset_id} ${c.entry.result_id} ${c.entry.tags.join(' ')} ${c.result?.summary ?? ''} ${c.result?.humanRevision?.dimensions.map((d) => d.interpretation).join(' ') ?? ''}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  return (
    <WorkspacePage active="/knowledge">
      <h1 className="text-2xl font-semibold">视觉知识库</h1>
      <p className="text-sm text-muted-foreground">
        AI 提出分析 → 人工校准 →
        形成知识资产。仅展示后端判定已确认、真实且证据有效的案例。
      </p>
      <div className="flex flex-wrap gap-6 rounded-xl border border-white/10 p-4">
        <p>已收录案例数量：{loading ? '读取中' : cases.length}</p>
        <p>
          已确认标签数量：{hasTagRevisions ? confirmedTags.size : '—'}{' '}
          <span className="text-sm text-muted-foreground">
            {hasTagRevisions
              ? '按当前人工版本统计'
              : `无独立标签确认字段；已审核案例关联标签 ${tags.length} 种`}
          </span>
        </p>
        <p>
          最近更新时间：
          {times.length
            ? new Date(Math.max(...times)).toLocaleString()
            : '暂无时间数据'}
          <span className="block text-xs text-muted-foreground">
            按已加载反馈时间计算
          </span>
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Input
          aria-label="搜索案例"
          placeholder="搜索案例、文件名或分析内容"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="max-w-sm"
        />
        <label>
          标签{' '}
          <select
            aria-label="按标签筛选"
            className="rounded border bg-background p-2"
            value={tag}
            onChange={(e) => setTag(e.target.value)}
          >
            <option value="">全部</option>
            {tags.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </label>
        <label>
          审核状态{' '}
          <select
            aria-label="按审核状态筛选"
            className="rounded border bg-background p-2"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="">全部</option>
            {[
              '已确认',
              '已人工修改',
              '审核中',
              '需重新审核',
              '暂无人工审核记录',
            ].map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </label>
        <Button
          variant="outline"
          disabled={loading}
          onClick={() => void refresh()}
        >
          刷新
        </Button>
      </div>
      {error && (
        <p role="alert">读取失败：{error}。已有内容可能已过期，请重试。</p>
      )}
      {loading ? (
        <output>正在读取知识资产…</output>
      ) : (
        filtered.length === 0 && (
          <p>暂无符合条件的知识案例。完成真实分析的五维审核后再刷新。</p>
        )
      )}
      {!loading &&
        filtered.map(({ entry, result, error: detailError }) => (
          <article
            key={entry.result_id}
            className="rounded-xl border border-white/10 bg-card p-4"
          >
            <div className="mb-4 flex flex-wrap gap-4">
              <Link
                aria-label={`预览 ${entry.original_filename}`}
                href={`/knowledge/${entry.result_id}`}
              >
                <img
                  src={entry.preview_url}
                  alt={entry.original_filename}
                  className="h-36 w-48 object-contain"
                />
              </Link>
              <div className="min-w-0 break-all">
                <Link
                  className="font-semibold underline"
                  href={`/knowledge/${entry.result_id}`}
                >
                  {entry.original_filename}
                </Link>
                <p className="text-sm">asset_id：{entry.asset_id}</p>
                <p className="text-sm">result_id：{entry.result_id}</p>
                <p className="text-sm">
                  {entry.tags.length
                    ? `已审核案例关联标签：${entry.tags.join(' · ')}`
                    : '暂无标签'}
                </p>
              </div>
            </div>
            {detailError && <p role="alert">{detailError}</p>}
            <DeleteKnowledgeCase id={entry.result_id} name={entry.original_filename} onDeleted={() => {
              sequence.current++;
              setLoading(false);
              setCases(current => current.filter(item => item.entry.result_id !== entry.result_id));
            }} />
            <KnowledgeEvidence result={result} />
          </article>
        ))}
    </WorkspacePage>
  );
}
