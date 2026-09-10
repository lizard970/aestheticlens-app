import type { AnalysisResult, UploadedAsset } from './aesthetic-domain';

export interface ReviewItem {
  id: string;
  name: string;
  asset?: UploadedAsset;
  result?: AnalysisResult;
  error?: string;
}
export interface ReviewQueue {
  items: ReviewItem[];
  currentId: string | null;
  dimension: string;
}
export const emptyQueue: ReviewQueue = {
  items: [],
  currentId: null,
  dimension: 'lighting',
};

export function canRetry(item: ReviewItem) {
  return !item.result || item.result.provenance.semantic?.status === 'failed';
}

export function reviewed(result: AnalysisResult | undefined, code: string) {
  const status = result?.humanRevision?.dimensions.find(
    (d) => d.code === code,
  )?.review_status;
  return status === 'accept' || status === 'edit';
}

export function reviewStatus(
  item: ReviewItem,
): 'pending' | 'reviewing' | 'completed' {
  if (!item.result) return 'pending';
  return item.result.dimensions.length === 5 &&
    item.result.dimensions.every((d) => reviewed(item.result, d.code))
    ? 'completed'
    : 'reviewing';
}

export function nextReview(
  queue: ReviewQueue,
): Pick<ReviewQueue, 'currentId' | 'dimension'> {
  const index = queue.items.findIndex((item) => item.id === queue.currentId);
  const ordered = [
    ...queue.items.slice(index + 1),
    ...queue.items.slice(0, index + 1),
  ];
  const same = ordered.find(
    (item) =>
      !item.error &&
      item.result?.dimensions.some((d) => d.code === queue.dimension) &&
      !reviewed(item.result, queue.dimension),
  );
  if (same) return { currentId: same.id, dimension: queue.dimension };
  for (const item of ordered) {
    if (item.error) continue;
    const dimension = item.result?.dimensions.find(
      (d) => !reviewed(item.result, d.code),
    );
    if (dimension) return { currentId: item.id, dimension: dimension.code };
  }
  return { currentId: queue.currentId, dimension: queue.dimension };
}

// Files and preview data live in IndexedDB, not size-limited localStorage or transient blob URLs.
async function database() {
  return new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open('aestheticlens-review', 1);
    request.onupgradeneeded = () =>
      request.result.createObjectStore('workspace');
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export async function readQueue(): Promise<ReviewQueue> {
  const db = await database();
  try {
    return await new Promise<ReviewQueue>((resolve, reject) => {
      const request = db
        .transaction('workspace')
        .objectStore('workspace')
        .get('queue');
      request.onsuccess = () =>
        resolve((request.result as ReviewQueue | undefined) ?? emptyQueue);
      request.onerror = () => reject(request.error);
    });
  } finally {
    db.close();
  }
}

export async function writeQueue(queue: ReviewQueue) {
  const db = await database();
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = db.transaction('workspace', 'readwrite');
      transaction.objectStore('workspace').put(queue, 'queue');
      transaction.oncomplete = () => resolve();
      transaction.onabort = () => reject(transaction.error);
      transaction.onerror = () => reject(transaction.error);
    });
  } finally {
    db.close();
  }
}
