import type { AnalysisResult } from '@/lib/aesthetic-domain';
import { analysisPresentation } from '@/lib/analysis-presentation';

// The adapter appends this labelled suffix; split only that explicit boundary.
export function splitAnalysisLimitation(text = '') {
  const match = /(?:^|\n)不确定性[：:]\s*/.exec(text);
  return match
    ? {
        text: text.slice(0, match.index),
        limitation: text.slice(match.index + match[0].length),
      }
    : { text, limitation: '' };
}

export function SemanticStatus({ result }: { result: AnalysisResult }) {
  const warnings = [
    ...new Set([
      ...result.warnings,
      ...(result.features ?? []).flatMap((feature) => feature.warnings ?? []),
    ]),
  ];
  const limitations = new Set<string>();
  for (const [code, reason] of Object.entries(
    result.provenance.semantic?.uncertainty ?? {},
  )) {
    limitations.add(
      `不确定性 · ${result.dimensions.find((d) => d.code === code)?.label ?? code}：${reason}`,
    );
  }
  for (const dimension of result.dimensions) {
    for (const text of [dimension.observation, dimension.interpretation]) {
      const { limitation } = splitAnalysisLimitation(text);
      if (limitation)
        limitations.add(`不确定性 · ${dimension.label}：${limitation}`);
    }
  }
  return (
    <>
      <p className="mb-2 text-xs font-medium text-amber-200">
        {analysisPresentation(result).semantics}
      </p>
      <details className="my-3 rounded-lg border border-white/10 p-3">
        <summary className="cursor-pointer text-sm text-muted-foreground">
          分析限制 · {warnings.length} 项警告，{limitations.size} 项不确定性
        </summary>
        {warnings.map((warning, index) => (
          <p
            role="alert"
            key={`${index}:${warning}`}
            className="text-sm text-amber-200"
          >
            {warning}
          </p>
        ))}
        {[...limitations].map((reason) => (
          <p
            key={reason}
            className="whitespace-pre-wrap text-sm text-amber-200"
          >
            {reason}
          </p>
        ))}
        {warnings.length === 0 && limitations.size === 0 && (
          <p className="text-sm text-muted-foreground">
            暂无已记录的分析限制。
          </p>
        )}
      </details>
    </>
  );
}
