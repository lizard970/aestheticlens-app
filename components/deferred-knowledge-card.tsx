'use client';
import { useEffect, useRef, useState } from 'react';
import { knowledgeListCache } from '@/lib/knowledge-list-cache';

export function DeferredKnowledgeCard({
  id,
  children,
}: {
  id: string;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(
    () => typeof IntersectionObserver === 'undefined',
  );
  useEffect(() => {
    const element = ref.current;
    if (!element || typeof IntersectionObserver === 'undefined') return;
    const remember = () => {
      const height = element.getBoundingClientRect().height;
      if (height > 0) knowledgeListCache.heights.set(id, height);
    };
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) remember();
        setVisible(entry.isIntersecting);
      },
      { rootMargin: '600px' },
    );
    observer.observe(element);
    return () => {
      remember();
      observer.disconnect();
    };
  }, [id]);
  return (
    <div
      ref={ref}
      className="mb-4 break-inside-avoid"
      style={
        visible
          ? undefined
          : { height: knowledgeListCache.heights.get(id) ?? 440 }
      }
    >
      {visible ? (
        children
      ) : (
        <div
          aria-label="案例占位"
          className="h-full rounded-xl border border-white/10"
        />
      )}
    </div>
  );
}
