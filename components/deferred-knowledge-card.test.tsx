import { act, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { DeferredKnowledgeCard } from './deferred-knowledge-card';
import { knowledgeListCache } from '@/lib/knowledge-list-cache';

it('mounts near the viewport and unmounts distant card contents while retaining height', () => {
  let notify: (entries: Array<{ isIntersecting: boolean }>) => void = () => {};
  const disconnect = vi.fn();
  vi.stubGlobal(
    'IntersectionObserver',
    class {
      constructor(callback: typeof notify) {
        notify = callback;
      }
      observe() {}
      disconnect = disconnect;
    },
  );
  const rect = vi
    .spyOn(HTMLElement.prototype, 'getBoundingClientRect')
    .mockReturnValue({ height: 390 } as DOMRect);
  try {
    const view = render(
      <DeferredKnowledgeCard id="deferred">
        <p>Actual card</p>
      </DeferredKnowledgeCard>,
    );
    expect(screen.queryByText('Actual card')).not.toBeInTheDocument();
    act(() => notify([{ isIntersecting: true }]));
    expect(screen.getByText('Actual card')).toBeInTheDocument();
    act(() => notify([{ isIntersecting: false }]));
    expect(screen.queryByText('Actual card')).not.toBeInTheDocument();
    expect(screen.getByLabelText('案例占位').parentElement).toHaveStyle({
      height: '390px',
    });
    view.unmount();
    expect(disconnect).toHaveBeenCalled();
    expect(knowledgeListCache.heights.get('deferred')).toBe(390);
  } finally {
    rect.mockRestore();
    vi.unstubAllGlobals();
  }
});
