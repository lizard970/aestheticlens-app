"""Resolve only stored successful computation; no inferred image regions."""
import json
from pathlib import Path

from .models import AnalysisResult, ResolvedEvidence
from .semantic_adapter import feature_evidence


def resolve_evidence(result: AnalysisResult) -> list[ResolvedEvidence]:
    values = feature_evidence(result.features)
    labels = json.loads((Path(__file__).resolve().parent.parent / "config" / "evidence_labels.json").read_text(encoding="utf-8"))
    features = {feature.extractor_code: feature for feature in result.features}
    references: dict[str, list[str]] = {}
    for dimension in result.dimensions:
        for ref in dimension.evidence_refs:
            if dimension.code not in references.setdefault(ref, []):
                references[ref].append(dimension.code)
    output = []
    for ref, dimensions in references.items():
        if ref not in values:
            output.append(ResolvedEvidence(id=ref, label="Mock 引用" if ref.startswith("mock:") else "无法解析的证据",
                                          status="mock" if ref.startswith("mock:") else "invalid", supports_dimensions=dimensions))
            continue
        code, pointer = ref[len("feature:"):].split("#", 1)
        output.append(ResolvedEvidence(id=ref, label=labels.get(ref, f"{features[code].method} · {pointer}"),
                                      value=values[ref], extractor_code=code, field_path=pointer,
                                      status="resolved", supports_dimensions=dimensions))
    return output
