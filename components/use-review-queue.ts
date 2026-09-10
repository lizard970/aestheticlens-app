'use client';

import { useEffect, useRef, useState } from 'react';
import { ApiAnalysisProvider } from '@/lib/api-analysis-provider';
import type { AnalysisResult, UploadedAsset } from '@/lib/aesthetic-domain';
import {
  emptyQueue,
  nextReview,
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
      const items = await Promise.all(
        restored.items.map(async (item) => {
          if (!item.result) return item;
          try {
            return {
              ...item,
              result: await reviewProvider.getResult(item.result.id),
              error: undefined,
            };
          } catch {
            return {
              ...item,
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
      state.current = { ...restored, items };
      setQueue(state.current);
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
            name: `image_${String(state.current.items.length + added.length + 1).padStart(3, '0')}`,
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

  async function analyze() {
    if (lock.current || !ready) return;
    lock.current = true;
    setBusy(true);
    setError(null);
    try {
      for (const item of state.current.items.filter(
        (item) => item.asset && !item.result,
      )) {
        if (!alive.current) break;
        update((current) => ({
          ...current,
          items: current.items.map((row) =>
            row.id === item.id ? { ...row, error: undefined } : row,
          ),
        }));
        try {
          const result = await reviewProvider.analyze(item.asset!);
          update((current) => ({
            ...current,
            items: current.items.map((row) =>
              row.id === item.id ? { ...row, result } : row,
            ),
          }));
        } catch {
          update((current) => ({
            ...current,
            items: current.items.map((row) =>
              row.id === item.id
                ? { ...row, error: '分析失败，可重试；其他图片继续处理。' }
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
      return { ...updated, ...nextReview(updated) };
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
    select: (id: string) =>
      update((current) => ({ ...current, currentId: id })),
    dimension: (code: string) =>
      update((current) => ({ ...current, dimension: code })),
  };
}
