'use client';

/* eslint-disable @next/next/no-img-element -- Local data previews and existing API image URLs are displayed without an image proxy. */

import { useRef, useState } from 'react';
import { Aperture } from 'lucide-react';
import { WorkspaceNavigation } from './workspace-navigation';
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogCancel,
  AlertDialogAction,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { DimensionReview } from '@/components/dimension-review';
import { ResultHistory } from '@/components/result-history';
import { ComputationalFeatures } from '@/components/computational-features';
import { ColorComputationalFeatures } from '@/components/color-computational-features';
import {
  CompositionComputationalFeatures,
  SpaceComputationalFeatures,
} from '@/components/spatial-composition-features';
import {
  SemanticStatus,
  splitAnalysisLimitation,
} from '@/components/semantic-status';
import { reviewProvider, useReviewQueue } from '@/components/use-review-queue';
import {
  reviewed,
  reviewStatus,
  canRetry,
  canReview,
  phases,
} from '@/lib/review-queue';

const labels = {
  pending: '待分析',
  feature_processing: '分析中 · 特征提取',
  semantic_processing: '分析中 · 语义调用',
  review_pending: '待审核',
  reviewing: '审核中',
  completed: '审核完成',
  failed: '失败',
};

export function AestheticWorkspace() {
  const input = useRef<HTMLInputElement>(null);
  const flow = useReviewQueue();
  const [saving, setSaving] = useState(false);
  const [removing, setRemoving] = useState(false);
  const { queue } = flow;
  const index = queue.items.findIndex((item) => item.id === queue.currentId);
  const item = queue.items[index];
  const result = item?.result;
  const disabled = !flow.ready || flow.busy || saving;
  const navigationDisabled = !flow.ready || saving;
  const preview = item?.asset?.previewUrl ?? result?.previewUrl;
  const dimensionCode = result?.dimensions.some(
    (d) => d.code === queue.dimension,
  )
    ? queue.dimension
    : result?.dimensions[0]?.code;
  const complete = queue.items.filter(
    (row) => reviewStatus(row) === 'completed',
  ).length;

  return (
    <main className="min-h-screen bg-background text-foreground">
      <header className="flex h-16 items-center gap-3 border-b border-white/10 px-5">
        <Aperture className="size-6 text-amber-300" />
        <div>
          <p className="font-semibold">AestheticLens</p>
          <p className="text-sm text-muted-foreground">
            人工审核闭环的视觉分析系统
          </p>
        </div>
      </header>
      <div className="mx-auto grid max-w-[1800px] lg:grid-cols-[180px_minmax(0,1fr)]">
        <WorkspaceNavigation active="/" />
        <section className="min-w-0 p-4 lg:p-5">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h1 className="text-2xl font-semibold">素材分析</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                逐维确认或修改，将 AI 判断校准为人工知识。
              </p>
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                disabled={disabled}
                onClick={() => input.current?.click()}
              >
                上传图片
              </Button>
              <Button
                disabled={disabled || !queue.items.some(canRetry)}
                onClick={() => void flow.analyze()}
              >
                {flow.busy ? '处理中…' : '分析未完成图片'}
              </Button>
            </div>
          </div>
          {item && (
            <div className="mb-3 flex flex-wrap gap-2">
              {canRetry(item) && (
                <Button
                  variant="outline"
                  disabled={disabled}
                  onClick={() => void flow.analyze(item.id)}
                >
                  重试当前图片
                </Button>
              )}
              <Button
                variant="outline"
                disabled={disabled}
                onClick={() => setRemoving(true)}
              >
                删除当前图片
              </Button>
              <span className="text-sm text-muted-foreground">
                特征完成后重试仅调用语义分析；删除仅移出本地队列。
              </span>
            </div>
          )}
          <AlertDialog open={removing} onOpenChange={setRemoving}>
            <AlertDialogContent>
              <AlertDialogTitle>移除当前图片？</AlertDialogTitle>
              <AlertDialogDescription>
                本地队列中的图片和未保存修改将移除。服务器原图、分析和审核记录不会删除。
              </AlertDialogDescription>
              <AlertDialogCancel>取消</AlertDialogCancel>
              <AlertDialogAction
                onClick={() => {
                  flow.removeCurrent();
                  setRemoving(false);
                }}
              >
                确认移除
              </AlertDialogAction>
            </AlertDialogContent>
          </AlertDialog>
          <input
            ref={input}
            aria-label="上传图片"
            type="file"
            multiple
            accept="image/jpeg,image/png,image/webp"
            className="sr-only"
            disabled={disabled}
            onChange={(event) => {
              void flow.upload(Array.from(event.target.files ?? []));
              event.target.value = '';
            }}
          />
          <ResultHistory
            load={() => reviewProvider.history()}
            onSelect={(id) => void flow.openHistory(id)}
            disabled={disabled}
          />
          {flow.error && (
            <p role="alert" className="mb-3 text-sm text-red-300">
              {flow.error}
            </p>
          )}
          {!flow.ready && <output>正在恢复审核队列…</output>}
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2 text-sm">
            <p aria-live="polite">
              图片 {index < 0 ? 0 : index + 1} / {queue.items.length} · 已完成{' '}
              {complete} / {queue.items.length}
            </p>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={navigationDisabled || index <= 0}
                onClick={() => flow.select(queue.items[index - 1].id)}
              >
                上一张
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={
                  navigationDisabled ||
                  index < 0 ||
                  index >= queue.items.length - 1
                }
                onClick={() => flow.select(queue.items[index + 1].id)}
              >
                下一张
              </Button>
            </div>
          </div>
          <div className="grid items-start gap-4 xl:grid-cols-[150px_minmax(0,1fr)_minmax(380px,1fr)]">
            <aside
              aria-label="图片审核队列"
              className="flex gap-2 overflow-auto rounded-xl border border-white/10 p-2 xl:max-h-[75vh] xl:flex-col"
            >
              {queue.items.length === 0 && (
                <p className="p-2 text-sm text-muted-foreground">
                  上传后生成图片任务
                </p>
              )}
              {queue.items.map((row) => (
                <button
                  key={row.id}
                  type="button"
                  aria-current={row.id === queue.currentId ? 'true' : undefined}
                  aria-label={`${row.name} ${reviewStatus(row)}`}
                  disabled={navigationDisabled}
                  onClick={() => flow.select(row.id)}
                  className={`w-32 shrink-0 rounded-lg border p-2 text-left xl:w-full ${row.id === queue.currentId ? 'border-amber-300 bg-amber-300/5' : 'border-white/10'}`}
                >
                  {(row.asset?.previewUrl ?? row.result?.previewUrl) && (
                    <img
                      src={row.asset?.previewUrl ?? row.result?.previewUrl}
                      alt={row.asset?.file.name ?? row.name}
                      className="mb-2 aspect-video w-full object-contain"
                    />
                  )}
                  <span className="block text-sm font-medium">{row.name}</span>
                  <span className="block text-xs text-muted-foreground">
                    {labels[reviewStatus(row)]} · {reviewStatus(row)}
                  </span>
                  {row.error && (
                    <span className="block text-xs text-red-300">需重试</span>
                  )}
                  <span className="block text-xs">
                    {phases(row).feature_analysis_status === 'completed'
                      ? '✓ 特征完成'
                      : phases(row).feature_analysis_status === 'failed'
                        ? '⚠️ 特征失败'
                        : '特征未完成'}
                  </span>
                  <span className="block text-xs">
                    {phases(row).semantic_analysis_status === 'completed'
                      ? '✓ 语义完成'
                      : phases(row).semantic_analysis_status === 'failed'
                        ? '⚠️ 语义分析失败'
                        : '语义未完成'}
                  </span>
                </button>
              ))}
            </aside>
            <section
              aria-label="当前图片预览"
              className="rounded-xl border border-white/10 bg-card p-3 xl:sticky xl:top-4"
            >
              <h2 className="mb-3 break-all text-sm">
                {item?.asset?.file.name ?? item?.name ?? '选择图片'}
              </h2>
              <div
                className="flex min-h-80 items-center justify-center rounded-lg bg-black/30 p-3"
                onDragOver={(event) => event.preventDefault()}
                onDrop={(event) => {
                  event.preventDefault();
                  if (!disabled)
                    void flow.upload(Array.from(event.dataTransfer.files));
                }}
              >
                {preview ? (
                  <img
                    src={preview}
                    alt="当前审核图片"
                    className="max-h-[65vh] max-w-full object-contain"
                  />
                ) : (
                  <button
                    type="button"
                    disabled={disabled}
                    onClick={() => input.current?.click()}
                    className="rounded-xl border border-dashed border-white/20 p-8 text-center"
                  >
                    拖入图片，或点击上传
                    <span className="mt-2 block text-sm text-muted-foreground">
                      支持单张或多张 JPG、PNG、WebP
                    </span>
                  </button>
                )}
              </div>
              {item?.error && (
                <p role="alert" className="mt-3 text-sm text-red-300">
                  {item.error}
                </p>
              )}
              {item?.result?.semantic_error_message && (
                <p role="alert" className="mt-3 text-sm text-red-300">
                  语义分析失败：{item.result.semantic_error_message}
                </p>
              )}
            </section>
            <section
              aria-label="五维人工审核"
              className="min-w-0 rounded-xl border border-white/10 bg-card p-4"
            >
              {!result ? (
                <p className="py-12 text-center text-muted-foreground">
                  {flow.busy
                    ? '正在逐图分析，单张失败不会中断队列。'
                    : '分析完成后，在这里逐维确认或修改。'}
                </p>
              ) : (
                <>
                  <h2 className="text-lg font-semibold">五维人工审核</h2>
                  <p className="my-2 text-sm">{result.summary}</p>
                  <SemanticStatus key={result.id} result={result} />
                  <p className="my-3 text-sm text-muted-foreground">
                    保存成功后，自动切换当前图片的下一未审核维度；五维完成后进入下一张。
                  </p>
                  <Tabs
                    value={dimensionCode}
                    onValueChange={(value) => {
                      if (!saving) flow.dimension(String(value));
                    }}
                  >
                    <TabsList
                      variant="line"
                      className="h-auto w-full flex-wrap justify-start"
                    >
                      {result.dimensions.map((d) => (
                        <TabsTrigger
                          key={d.code}
                          value={d.code}
                          disabled={saving}
                        >
                          {d.label}
                          {reviewed(result, d.code) ? ' ✓' : ''}
                        </TabsTrigger>
                      ))}
                    </TabsList>
                    {result.dimensions.map((d) => (
                      <TabsContent key={d.code} value={d.code} className="pt-3">
                        <article
                          aria-label={`${d.label}审核卡片`}
                          className="space-y-3 rounded-xl border border-white/10 p-3"
                        >
                          <h3 className="font-medium">{d.label} · AI 结果</h3>
                          <p className="text-sm leading-6">
                            {splitAnalysisLimitation(d.observation).text}
                          </p>
                          <p className="text-sm leading-6">
                            {splitAnalysisLimitation(d.interpretation).text}
                          </p>
                          {d.code === 'style' && (
                            <p className="text-sm">
                              风格标签：{result.tags.join(' · ') || '暂无'}
                            </p>
                          )}
                          <DimensionReview
                            key={`${result.id}:${d.code}`}
                            result={result}
                            dimension={d}
                            disabled={!canReview(item)}
                            onPendingChange={(pending) => {
                              setSaving(pending);
                              if (pending) flow.beginReview();
                            }}
                            save={(id, feedback) =>
                              reviewProvider.saveFeedback(id, feedback)
                            }
                            onSaved={flow.saved}
                          />
                          <details>
                            <summary className="cursor-pointer text-sm text-muted-foreground">
                              查看计算特征
                            </summary>
                            {d.code === 'lighting' && (
                              <ComputationalFeatures
                                features={result.features}
                                completionStatus={result.completionStatus}
                                resultWarnings={result.warnings}
                                hideWarnings
                              />
                            )}
                            {d.code === 'color' && (
                              <ColorComputationalFeatures
                                features={result.features}
                              />
                            )}
                            {d.code === 'space' && (
                              <SpaceComputationalFeatures
                                features={result.features}
                              />
                            )}
                            {d.code === 'composition' && (
                              <CompositionComputationalFeatures
                                features={result.features}
                              />
                            )}
                          </details>
                        </article>
                      </TabsContent>
                    ))}
                  </Tabs>
                </>
              )}
            </section>
          </div>
        </section>
      </div>
    </main>
  );
}
