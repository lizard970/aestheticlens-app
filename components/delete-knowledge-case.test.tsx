import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { DeleteKnowledgeCase } from './delete-knowledge-case';
import { deleteKnowledgeCase } from '@/lib/knowledge-api';

vi.mock('@/lib/knowledge-api', () => ({ deleteKnowledgeCase: vi.fn() }));

it('requires confirmation, retains the case on failure and updates only on success', async () => {
  const removed = vi.fn();
  vi.mocked(deleteKnowledgeCase).mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(undefined);
  render(<DeleteKnowledgeCase id="case-id" name="image.png" onDeleted={removed} />);
  fireEvent.click(screen.getByRole('button', { name: '删除案例' }));
  expect(deleteKnowledgeCase).not.toHaveBeenCalled();
  fireEvent.click(await screen.findByRole('button', { name: '确认删除数据库记录' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('offline');
  expect(removed).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: '确认删除数据库记录' }));
  await waitFor(() => expect(removed).toHaveBeenCalledTimes(1));
  expect(deleteKnowledgeCase).toHaveBeenLastCalledWith('case-id');
});
