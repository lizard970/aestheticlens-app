'use client';

import { useRef, useState } from 'react';
import { deleteKnowledgeCase } from '@/lib/knowledge-api';
import { Button } from './ui/button';
import { AlertDialog, AlertDialogContent, AlertDialogTitle, AlertDialogDescription, AlertDialogCancel, AlertDialogAction } from './ui/alert-dialog';

export function DeleteKnowledgeCase({ id, name, onDeleted }: { id: string; name: string; onDeleted: () => void }) {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const lock = useRef(false);
  async function remove() {
    if (lock.current) return;
    lock.current = true; setPending(true); setError('');
    try {
      await deleteKnowledgeCase(id);
      setOpen(false);
      onDeleted();
    } catch (reason) { setError(reason instanceof Error ? reason.message : '删除失败，请重试'); }
    finally { lock.current = false; setPending(false); }
  }
  return <>
    <Button variant="outline" onClick={() => { setError(''); setOpen(true); }}>删除案例</Button>
    <AlertDialog open={open} onOpenChange={value => { if (!pending) setOpen(value); }}>
      <AlertDialogContent>
        <AlertDialogTitle>删除案例「{name}」？</AlertDialogTitle>
        <AlertDialogDescription>将删除此案例的分析、审核记录和检索索引，无法撤销；原始图片文件和图片存储数据保留。</AlertDialogDescription>
        {error && <p role="alert">删除失败：{error}</p>}
        <AlertDialogCancel disabled={pending}>取消</AlertDialogCancel>
        <AlertDialogAction disabled={pending} onClick={() => void remove()}>{pending ? '正在删除…' : '确认删除数据库记录'}</AlertDialogAction>
      </AlertDialogContent>
    </AlertDialog>
  </>;
}
