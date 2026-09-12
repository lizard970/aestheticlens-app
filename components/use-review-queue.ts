'use client';

import { useEffect, useRef, useState } from 'react';
import { ApiAnalysisProvider } from '@/lib/api-analysis-provider';
import type {
  AnalysisProgress,
  AnalysisResult,
  UploadedAsset,
} from '@/lib/aesthetic-domain';
import {
  emptyQueue,
  canRetry,
  canReview,
  phases,
  nextReview,
  reviewStatus,
  readQueue,
  writeQueue,
  type ReviewItem,
  type ReviewQueue,
} from '@/lib/review-queue';

export const reviewProvider = new ApiAnalysisProvider();

async function createAsset(file: File): Promise<UploadedAsset> {
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type))
    throw new Error('仅支持 JPG、PNG 和 WebP');
  const previewUrl = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === 'string') resolve(reader.result);
      else reject(new Error('文件读取失败'));
    };
    reader.onerror = () => reject(new Error('文件读取失败'));
    reader.readAsDataURL(file);
  });
  const dimensions = await new Promise<{ width: number; height: number }>(
    (resolve, reject) => {
      const image = new Image();
      image.onload = () =>
        resolve({ width: image.naturalWidth, height: image.naturalHeight });
      image.onerror = () => reject(new Error('图片损坏，无法读取'));
      image.src = previewUrl;
    },
  );
  return { id: crypto.randomUUID(), file, previewUrl, ...dimensions };
}

export function useReviewQueue() {
  const [queue, setQueue] = useState<ReviewQueue>(emptyQueue);
  const state = useRef(queue);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const writes = useRef(Promise.resolve());
  const alive = useRef(true);

  function update(change: (current: ReviewQueue) => ReviewQueue) {
    const next = change(state.current);
    state.current = next;
    if (alive.current) setQueue(next);
    writes.current = writes.current
      .then(() => writeQueue(next))
      .catch(() => {
        if (alive.current)
          setError(
            '浏览器保存失败，刷新可能丢失队列。服务器已保存的审核记录不受影响。',
          );
      });
  }

  useEffect(() => {
    alive.current = true;
    let cancelled = false;
    void (async () => {
      let restored = emptyQueue;
      try {
        restored = await readQueue();
      } catch {
        if (!cancelled) setError('无法恢复本地队列；请检查浏览器存储权限。');
      }
      const items: ReviewItem[] = await Promise.all(
        restored.items.map(async (item) => {
          if (!item.result) return { ...item, progress: undefined };
          try {
            return {
              ...item,
              result: await reviewProvider.getResult(item.result.id),
              error: undefined,
              progress: undefined,
            };
          } catch {
            return {
              ...item,
              progress: undefined,
              error:
                '服务器结果读取失败，当前为缓存；请重新读取历史记录后审核。',
            };
          }
        }),
      );
      const id = new URL(window.location.href).searchParams.get('result_id');
      if (id && !items.some((item) => item.result?.id === id)) {
        try {
          items.push({
            id,
            name: '历史素材',
            result: await reviewProvider.getResult(id),
          });
          restored = { ...restored, currentId: id };
        } catch {
          if (!cancelled) setError('历史结果读取失败。');
        }
      }
      if (cancelled) return;
      const linked = items.find((item) => item.result?.id === id);
      const active = items.filter(
        (item) =>
          reviewStatus(item) !== 'completed' &&
          !item.result?.humanRevision?.knowledge_excluded,
      );
      const currentId = linked?.id ?? restored.currentId;
      update(() => ({
        ...restored,
        items: active,
        currentId: active.some((item) => item.id === currentId)
          ? currentId
          : (active[0]?.id ?? null),
      }));
      if (linked) {
        const url = new URL(window.location.href);
        url.searchParams.delete('result_id');
        window.history.replaceState(null, '', url);
      }
      setReady(true);
    })();
    return () => {
      cancelled = true;
      alive.current = false;
    };
  }, []);

  async function upload(files: File[]) {
    if (lock.current || !ready || !files.length) return;
    lock.current = true;
    setBusy(true);
    setError(null);
    const added: ReviewItem[] = [];
    try {
      for (const file of files) {
        try {
          const asset = await createAsset(file);
          added.push({
            id: asset.id,
            asset,
            name: `image_${String(Math.max(0, ...state.current.items.map((item) => Number(item.name.replace('image_', '')) || 0)) + added.length + 1).padStart(3, '0')}`,
          });
        } catch (reason) {
          setError(
            `${file.name}：${reason instanceof Error ? reason.message : '读取失败'}；其他有效图片仍会加入队列。`,
          );
        }
      }
      if (added.length)
        update((current) => ({
          ...current,
          items: [...current.items, ...added],
          currentId: added[0].id,
        }));
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }

  async function analyze(onlyId?: string) {
    if (lock.current || !ready) return;
    lock.current = true;
    setBusy(true);
    setError(null);
    try {
      for (const item of state.current.items.filter(
        (item) => canRetry(item) && (!onlyId || item.id === onlyId),
      )) {
        if (!alive.current) break;
        update((current) => ({
          ...current,
          items: current.items.map((row) =>
            row.id === item.id
              ? {
                  ...row,
                  error: undefined,
                  progress: {
                    assetId: row.serverAssetId ?? '',
                    jobId: '',
                    feature_analysis_status:
                      phases(row).feature_analysis_status === 'completed'
                        ? 'completed'
                        : 'processing',
                    semantic_analysis_status:
                      phases(row).feature_analysis_status === 'completed'
                        ? 'processing'
                        : 'pending',
                  },
                }
              : row,
          ),
        }));
        try {
          const serverAssetId =
            item.serverAssetId ??
            item.result?.assetId ??
            item.result?.previewUrl?.match(/\/assets\/([^/]+)\/content/)?.[1];
          const onProgress = (progress: AnalysisProgress) =>
            update((current) => ({
              ...current,
              items: current.items.map((row) =>
                row.id === item.id
                  ? { ...row, progress, serverAssetId: progress.assetId }
                  : row,
              ),
            }));
          const result = serverAssetId
            ? await reviewProvider.analyzeExisting(
                serverAssetId,
                onProgress,
                phases(item).feature_analysis_status === 'completed',
              )
            : item.asset
              ? await reviewProvider.analyze(item.asset, onProgress)
              : await Promise.reject(new Error('原图不可用'));
          update((current) => ({
            ...current,
            items: current.items.map((row) =>
              row.id === item.id
                ? {
                    ...row,
                    result,
                    progress: undefined,
                    error: undefined,
                    reviewStarted: false,
                    serverAssetId: result.assetId ?? row.serverAssetId,
                  }
                : row,
            ),
          }));
        } catch (reason) {
          update((current) => ({
            ...current,
            items: current.items.map((row) =>
              row.id === item.id
                ? {
                    ...row,
                    progress: undefined,
                    error:
                      reason instanceof Error
                        ? reason.message
                        : '分析失败，可重试；其他图片继续处理。',
                  }
                : row,
            ),
          }));
        }
      }
    } finally {
      lock.current = false;
      if (alive.current) setBusy(false);
    }
  }

  async function openHistory(id: string) {
    if (lock.current || !ready) return;
    lock.current = true;
    setBusy(true);
    try {
      const result = await reviewProvider.getResult(id);
      update((current) => {
        const existing = current.items.find((item) => item.result?.id === id);
        return {
          ...current,
          currentId: existing?.id ?? id,
          items: existing
            ? current.items.map((item) =>
                item.id === existing.id
                  ? { ...item, result, error: undefined }
                  : item,
              )
            : [
                ...current.items,
                {
                  id,
                  name: `image_${String(current.items.length + 1).padStart(3, '0')}`,
                  result,
                },
              ],
        };
      });
    } catch {
      setError('历史结果读取失败，请重试。');
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }

  function saved(result: AnalysisResult) {
    update((current) => {
      const updated = {
        ...current,
        items: current.items.map((item) =>
          item.result?.id === result.id ? { ...item, result } : item,
        ),
      };
      const next = nextReview(updated);
      const items = updated.items.filter(
        (item) =>
          reviewStatus(item) !== 'completed' &&
          !item.result?.humanRevision?.knowledge_excluded,
      );
      return {
        ...updated,
        ...next,
        items,
        currentId: items.some((item) => item.id === next.currentId)
          ? next.currentId
          : (items.find(canReview)?.id ?? items[0]?.id ?? null),
      };
    });
  }

  return {
    queue,
    ready,
    busy,
    error,
    upload,
    analyze,
    openHistory,
    saved,
    excludeCurrent: async () => {
      const item = state.current.items.find(
        (row) => row.id === state.current.currentId,
      );
      if (!item?.result) return;
      const updated = await reviewProvider.saveFeedback(item.result.id, {
        feedback_type: 'edit',
        target_path: '/knowledge_excluded',
        corrected_value: true,
        comment: null,
        error_category: null,
        base_revision: item.result.humanRevision?.revision ?? 0,
      });
      saved(updated);
    },
    beginReview: () =>
      update((current) => ({
        ...current,
        items: current.items.map((item) =>
          item.id === current.currentId && canReview(item)
            ? { ...item, reviewStarted: true }
            : item,
        ),
      })),
    removeCurrent: () => {
      if (lock.current) return;
      update((current) => {
        const index = current.items.findIndex(
          (item) => item.id === current.currentId,
        );
        const items = current.items.filter(
          (item) => item.id !== current.currentId,
        );
        const url = new URL(window.location.href);
        url.searchParams.delete('result_id');
        window.history.replaceState(null, '', url);
        return {
          ...current,
          items,
          currentId: items[Math.min(index, items.length - 1)]?.id ?? null,
        };
      });
    },
    select: (id: string) =>
      update((current) => ({
        ...current,
        currentId: id,
        items: current.items.map((item) =>
          item.id === id && canReview(item)
            ? { ...item, reviewStarted: true }
            : item,
        ),
      })),
    dimension: (code: string) =>
      update((current) => ({ ...current, dimension: code })),
  };
}
