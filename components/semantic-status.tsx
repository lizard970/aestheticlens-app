import type { AnalysisResult } from '@/lib/aesthetic-domain';
import { analysisPresentation } from '@/lib/analysis-presentation';

export function SemanticStatus({ result }: { result: AnalysisResult }) {
  return (
    <>
      <p className="mb-2 text-xs font-medium text-amber-200">
        {analysisPresentation(result).semantics}
      </p>
      {result.warnings.map((warning, index) => (
        <p
          role="alert"
          key={`${index}:${warning}`}
          className="text-sm text-amber-200"
        >
          {warning}
        </p>
      ))}
      {Object.entries(result.provenance.semantic?.uncertainty ?? {}).map(
        ([code, reason]) => (
          <p key={code} className="text-sm text-amber-200">
            不确定性 ·{' '}
            {result.dimensions.find((d) => d.code === code)?.label ?? code}：
            {reason}
          </p>
        ),
      )}
    </>
  );
}
