'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';

export function ResultHistory({
  load,
  onSelect,
  disabled,
}: {
  load: () => Promise<
    Array<{ id: string; original_filename: string; created_at: string }>
  >;
  onSelect: (id: string) => void;
  disabled: boolean;
}) {
  const [items, setItems] = useState<Awaited<ReturnType<typeof load>>>([]);
  const [opened, setOpened] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      setItems(await load());
      setOpened(true);
    } catch {
      setError('无法读取历史记录');
    } finally {
      setLoading(false);
    }
  }
  return (
    <div className="mb-3 text-sm">
      <Button
        variant="outline"
        size="sm"
        disabled={disabled || loading}
        onClick={() => void refresh()}
      >
        读取历史记录
      </Button>
      {error && <p role="alert">{error}</p>}
      {opened && (
        <ul className="mt-2 max-h-40 space-y-1 overflow-auto">
          {items.length === 0 && <li>暂无历史记录</li>}
          {items.map((item) => (
            <li key={item.id}>
              <button
                disabled={disabled}
                type="button"
                className="text-left underline"
                onClick={() => onSelect(item.id)}
              >
                {item.original_filename} ·{' '}
                {new Date(item.created_at).toLocaleString()}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
