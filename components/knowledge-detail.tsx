'use client';
/* eslint-disable @next/next/no-img-element -- Original images come from the existing API. */
import { useEffect, useState } from 'react';
import Link from 'next/link';
import {
  ApiAnalysisProvider,
  API_BASE_URL,
  jsonRequest,
} from '@/lib/api-analysis-provider';
import type { AnalysisResult } from '@/lib/aesthetic-domain';
import { WorkspacePage } from './workspace-navigation';
import { KnowledgeEvidence } from './knowledge-page';
import { Button } from './ui/button';
import { DeleteKnowledgeCase } from './delete-knowledge-case';
import { knowledgeListCache } from '@/lib/knowledge-list-cache';

export function KnowledgeDetail({ id }: { id: string }) {
  const [result, setResult] = useState<AnalysisResult>();
  const [meta, setMeta] = useState<{
    asset_id: string;
    original_filename: string;
  }>();
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [deleted, setDeleted] = useState(false);
  useEffect(() => {
    let active = true;
    void new ApiAnalysisProvider()
      .getResult(id)
      .then(async (data) => {
        if (!active) return;
        setResult(data);
        setError('');
        const cached = knowledgeListCache.getSnapshot().items.find(item => item.result_id === id);
        if (cached) setMeta(cached);
        else if (data.assetId) {
          try {
            const asset = await jsonRequest<{ id: string; original_filename: string }>(`${API_BASE_URL}/assets/${data.assetId}`);
            if (active) setMeta({ asset_id: asset.id, original_filename: asset.original_filename });
          } catch { /* Optional metadata; never load the full analysis history. */ }
        }
      })
      .catch(() => {
        if (active) setError('案例读取失败或不存在，请重试。');
      });
    return () => {
      active = false;
    };
  }, [id, attempt]);
  return (
    <WorkspacePage active="/knowledge">
      <Link href="/knowledge" scroll={false} className="underline">
        返回视觉知识库
      </Link>
      <h1 className="text-2xl font-semibold">案例详情</h1>
      <p className="break-all">
        {meta?.original_filename ?? '文件名未加载'} · asset_id：
        {meta?.asset_id ?? '未加载'} · result_id：{id}
      </p>
      {error && (
        <p role="alert">
          {error}
          <Button variant="outline" onClick={() => setAttempt((n) => n + 1)}>
            重试
          </Button>
        </p>
      )}
      {deleted && <p>案例数据库记录已删除，原始图片保留。</p>}
      {!deleted && !result && !error && <output>正在读取案例…</output>}
      {!deleted && result && (
        <>
          <DeleteKnowledgeCase id={id} name={meta?.original_filename ?? id} onDeleted={() => { knowledgeListCache.remove(id); setDeleted(true); }} />
          <Link
            href={`/?result_id=${encodeURIComponent(id)}`}
            className="underline"
          >
            进入人工审核
          </Link>
          {result.previewUrl && (
            <img
              src={result.previewUrl}
              alt={meta?.original_filename ?? '案例原图'}
              className="max-h-[65vh] max-w-full object-contain"
            />
          )}
          <h2 className="text-lg">AI 分析结果</h2>
          <p>{result.summary}</p>
          <KnowledgeEvidence result={result} full />
        </>
      )}
    </WorkspacePage>
  );
}
