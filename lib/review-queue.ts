import type {
  AnalysisProgress,
  AnalysisResult,
  UploadedAsset,
} from './aesthetic-domain';

export interface ReviewItem {
  id: string;
  name: string;
  asset?: UploadedAsset;
  result?: AnalysisResult;
  error?: string;
  progress?: AnalysisProgress;
  serverAssetId?: string;
  reviewStarted?: boolean;
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
  return (
    !item.progress &&
    (!item.result ||
      phases(item).feature_analysis_status !== 'completed' ||
      phases(item).semantic_analysis_status !== 'completed')
  );
}

export function phases(item: ReviewItem) {
  return (
    item.progress ?? {
      feature_analysis_status:
        item.result?.feature_analysis_status ??
        (item.result ? 'completed' : 'pending'),
      semantic_analysis_status:
        item.result?.semantic_analysis_status ??
        (item.result?.provenance.semantic?.status === 'failed'
          ? 'failed'
          : item.result
            ? 'completed'
            : 'pending'),
    }
  );
}

export function canReview(item?: ReviewItem) {
  return (
    !!item?.result &&
    !item.error &&
    !item.progress &&
    phases(item).feature_analysis_status === 'completed' &&
    phases(item).semantic_analysis_status === 'completed'
  );
}

export function reviewed(result: AnalysisResult | undefined, code: string) {
  const status = result?.humanRevision?.dimensions.find(
    (d) => d.code === code,
  )?.review_status;
  return status === 'accept' || status === 'edit';
}

export function reviewStatus(
  item: ReviewItem,
):
  | 'pending'
  | 'feature_processing'
  | 'semantic_processing'
  | 'review_pending'
  | 'reviewing'
  | 'completed'
  | 'failed' {
  const stage = phases(item);
  if (stage.feature_analysis_status === 'processing')
    return 'feature_processing';
  if (stage.semantic_analysis_status === 'processing')
    return 'semantic_processing';
  if (
    item.error ||
    stage.feature_analysis_status === 'failed' ||
    stage.semantic_analysis_status === 'failed'
  )
    return 'failed';
  if (!canReview(item) || !item.result) return 'pending';
  return item.result.dimensions.length === 5 &&
    item.result.dimensions.every((d) => reviewed(item.result, d.code))
    ? 'completed'
    : item.reviewStarted ||
        item.result.humanRevision?.dimensions.some((d) =>
          reviewed(item.result, d.code),
        )
      ? 'reviewing'
      : 'review_pending';
}

export function nextReview(
  queue: ReviewQueue,
): Pick<ReviewQueue, 'currentId' | 'dimension'> {
  const index = queue.items.findIndex((item) => item.id === queue.currentId);
  const current = queue.items[index];
  if (current && canReview(current) && current.result) {
    const dimensions = current.result.dimensions;
    const dimensionIndex = dimensions.findIndex(
      (dimension) => dimension.code === queue.dimension,
    );
    const orderedDimensions = [
      ...dimensions.slice(dimensionIndex + 1),
      ...dimensions.slice(0, dimensionIndex + 1),
    ];
    const pendingDimension = orderedDimensions.find(
      (dimension) => !reviewed(current.result, dimension.code),
    );
    if (pendingDimension) {
      return { currentId: current.id, dimension: pendingDimension.code };
    }
  }

  const ordered = [
    ...queue.items.slice(index + 1),
    ...queue.items.slice(0, index + 1),
  ];
  for (const item of ordered) {
    if (!canReview(item)) continue;
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
