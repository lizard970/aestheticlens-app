'use client';

import { useId, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import type {
  AnalysisDimension,
  AnalysisResult,
  DimensionFeedback,
} from '@/lib/aesthetic-domain';

type Props = {
  result: AnalysisResult;
  dimension: AnalysisDimension;
  save: (id: string, feedback: DimensionFeedback) => Promise<AnalysisResult>;
  onSaved: (result: AnalysisResult) => void;
};

const statusLabels = {
  unreviewed: '未确认',
  accept: '已认可',
  edit: '已修订',
  reject: '已拒绝',
  flag_error: '已标记错误',
};

export function DimensionReview({ result, dimension, save, onSaved }: Props) {
  const formId = useId();
  const current = result.humanRevision?.dimensions.find(
    (item) => item.code === dimension.code,
  );
  const [editing, setEditing] = useState(false);
  const [observation, setObservation] = useState(
    current?.observation ?? dimension.observation,
  );
  const [interpretation, setInterpretation] = useState(
    current?.interpretation ?? dimension.interpretation,
  );
  const [note, setNote] = useState('');
  const [category, setCategory] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const evidence =
    result.resolvedEvidence?.filter((item) =>
      item.supports_dimensions.includes(dimension.code),
    ) ?? [];

  async function submit(type: DimensionFeedback['feedback_type']) {
    setPending(true);
    setError(null);
    try {
      const updated = await save(result.id, {
        feedback_type: type,
        target_path: `/dimensions/${dimension.code}`,
        ...(type === 'edit'
          ? { corrected_value: { observation, interpretation } }
          : {}),
        comment: note || undefined,
        error_category: category || undefined,
        base_revision: result.humanRevision?.revision ?? 0,
      });
      onSaved(updated);
      setEditing(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '保存失败，请重试');
    } finally {
      setPending(false);
    }
  }

  return (
    <section aria-label={`${dimension.label}证据与反馈`} className="space-y-3">
      <details className="rounded-lg border border-white/10 p-3">
        <summary className="cursor-pointer text-sm">
          Evidence · 计算证据（
          {evidence.filter((item) => item.status === 'resolved').length}）
        </summary>
        {evidence.length === 0 && (
          <p className="mt-2 text-sm text-muted-foreground">
            该维度没有已解析的计算证据。
          </p>
        )}
        {evidence.map((item) => (
          <p key={item.id} className="mt-2 text-sm">
            {item.label}：
            {item.status === 'resolved'
              ? String(item.value)
              : item.status === 'mock'
                ? 'Mock 占位，不是真实证据'
                : '引用无效，无法解析'}
          </p>
        ))}
      </details>
      <p className="text-sm">
        人工审核：{statusLabels[current?.review_status ?? 'unreviewed']} · 修订{' '}
        {result.humanRevision?.revision ?? 0}
      </p>
      {current?.feedback_id && (
        <div className="rounded-lg border border-cyan-300/20 p-3 text-sm">
          <p>最新人工版本 · 观察：{current.observation}</p>
          <p>解释：{current.interpretation}</p>
          <p className="mt-2 text-muted-foreground">
            上方模型原文保留；原始证据不自动为人工新解释背书。
          </p>
        </div>
      )}
      {editing && (
        <>
          <label className="block text-sm" htmlFor={`${formId}-observation`}>
            修改观察
            <Textarea
              id={`${formId}-observation`}
              aria-label="修改观察"
              value={observation}
              onChange={(event) => setObservation(event.target.value)}
            />
          </label>
          <label className="block text-sm" htmlFor={`${formId}-interpretation`}>
            修改解释
            <Textarea
              id={`${formId}-interpretation`}
              aria-label="修改解释"
              value={interpretation}
              onChange={(event) => setInterpretation(event.target.value)}
            />
          </label>
        </>
      )}
      <details>
        <summary className="cursor-pointer text-sm text-muted-foreground">
          备注与错误类别（选填）
        </summary>
        <label className="block text-sm" htmlFor={`${formId}-note`}>
          备注
          <Textarea
            id={`${formId}-note`}
            aria-label="反馈备注"
            value={note}
            onChange={(event) => setNote(event.target.value)}
          />
        </label>
        <label className="block text-sm">
          错误类别
          <input
            aria-label="错误类别"
            className="ml-2 rounded border border-white/15 bg-transparent p-1"
            value={category}
            onChange={(event) => setCategory(event.target.value)}
          />
        </label>
      </details>
      {error && (
        <p role="alert" className="text-sm text-red-300">
          {error}（保存未确认；刷新历史可核对服务器状态）
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={pending}
          onClick={() => void submit('accept')}
        >
          认可
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={pending}
          onClick={() => {
            setObservation(current?.observation ?? dimension.observation);
            setInterpretation(
              current?.interpretation ?? dimension.interpretation,
            );
            setEditing(true);
          }}
        >
          修改
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={pending}
          onClick={() => void submit('reject')}
        >
          拒绝
        </Button>
        {editing && (
          <Button
            size="sm"
            disabled={pending || !observation.trim() || !interpretation.trim()}
            onClick={() => void submit('edit')}
          >
            保存修订
          </Button>
        )}
      </div>
    </section>
  );
}
