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
      .then((data) => {
        if (active) setResult(data);
      })
      .catch(() => {
        if (active) setError('案例读取失败或不存在，请重试。');
      });
    void jsonRequest<{
      items: Array<{ id: string; asset_id: string; original_filename: string }>;
    }>(`${API_BASE_URL}/analysis-results`)
      .then((data) => {
        if (active) setMeta(data.items.find((item) => item.id === id));
      })
      .catch(() => {
        /* Optional file metadata is explicitly absent below. */
      });
    return () => {
      active = false;
    };
  }, [id, attempt]);
  return (
    <WorkspacePage active="/knowledge">
      <Link href="/knowledge" className="underline">
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
          <DeleteKnowledgeCase id={id} name={meta?.original_filename ?? id} onDeleted={() => setDeleted(true)} />
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
