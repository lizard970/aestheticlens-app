import {
  loadKnowledgePage,
  type KnowledgeCase,
  type KnowledgeFilters,
} from './knowledge-api';

const initial = {
  items: [] as KnowledgeCase[],
  next_cursor: null as string | null,
  filters: { tag: '', review_status: '', query: '' },
  loaded: false,
  loading: false,
  error: '',
};
let state = initial;
let generation = 0;
let pending: Promise<void> | null = null;
let scroll = 0;
const listeners = new Set<() => void>();
const heights = new Map<string, number>();
function publish(next: typeof state) {
  state = next;
  listeners.forEach((listener) => listener());
}

// Browser module cache survives client-side route changes. SSR always sees initial
// state; no server process/user data is loaded into this store during rendering.
export const knowledgeListCache = {
  getSnapshot: () => state,
  getServerSnapshot: () => initial,
  subscribe: (listener: () => void) => {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  },
  getScroll: () => scroll,
  saveScroll: (value: number) => {
    scroll = value;
  },
  heights,
  reset: () => {
    generation++;
    pending = null;
    scroll = 0;
    heights.clear();
    publish(initial);
  },
  remove: (id: string) => {
    // Discard in-flight pages that could reintroduce a deleted record.
    generation++;
    pending = null;
    heights.delete(id);
    publish({
      ...state,
      items: state.items.filter((item) => item.result_id !== id),
      loading: false,
    });
  },
  load: (
    reset = false,
    filters: KnowledgeFilters = state.filters,
  ): Promise<void> => {
    if (!reset && pending) return pending;
    if (!reset && state.loaded && !state.next_cursor) return Promise.resolve();
    const request = ++generation;
    const previous = state;
    const changed = JSON.stringify(filters) !== JSON.stringify(state.filters);
    if (changed) scroll = 0;
    publish({
      ...(changed ? initial : state),
      filters,
      loading: true,
      error: '',
    });
    pending = loadKnowledgePage(filters, reset ? null : state.next_cursor)
      .then((page) => {
        if (request !== generation) return;
        const existing = reset ? [] : previous.items;
        const ids = new Set(existing.map((item) => item.result_id));
        publish({
          ...state,
          items: [
            ...existing,
            ...page.items.filter((item) => !ids.has(item.result_id)),
          ],
          next_cursor: page.next_cursor,
          loaded: true,
          loading: false,
        });
      })
      .catch((reason) => {
        if (request === generation)
          publish({
            ...state,
            loading: false,
            error: reason instanceof Error ? reason.message : '读取失败',
          });
      })
      .finally(() => {
        if (request === generation) pending = null;
      });
    return pending;
  },
};
