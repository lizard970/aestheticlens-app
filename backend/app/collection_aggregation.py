from collections import Counter, defaultdict
import math

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import cdist, pdist

from .reviews import ReviewService


def aggregate_collection(repository, items):
    completed = []
    for item in items:
        if item.status in {"succeeded", "partial"} and item.result_id:
            result = repository.get_result(item.result_id)
            if result:
                completed.append((item, result))
    distributions, semantics = defaultdict(list), defaultdict(list)
    tags, modes, vectors = Counter(), Counter(), []
    for item, result in completed:
        values = {}
        for feature in result.features:
            if feature.status != "succeeded":
                continue
            # Scalar top-level measurements only; never flatten histogram bins or metadata arrays.
            for key, value in feature.values.items():
                if type(value) in {int, float} and math.isfinite(value):
                    ref = f"feature:{feature.extractor_code}#/{key}"
                    distributions[ref].append(value)
                    values[ref] = value
        vectors.append(values)
        modes[result.provenance.get("mode", "unknown")] += 1
        revision = ReviewService(repository).revision(result.id)
        semantic_status = result.provenance.get("semantic", {}).get("status")
        if semantic_status not in {"succeeded", "mock"}:
            continue
        style = next((d for d in revision.dimensions if d.code == "style"), None)
        if style and style.review_status not in {"reject", "flag_error"}:
            tags.update(set(result.tags))
        for dimension in revision.dimensions:
            if dimension.review_status not in {"reject", "flag_error"}:
                semantics[dimension.code].append({"item_id": str(item.id), "result_id": str(result.id),
                    "interpretation": dimension.interpretation, "review_status": dimension.review_status,
                    "semantic_status": semantic_status})
    stats = {ref: {"count": len(values), "min": min(values), "max": max(values),
                   "mean": float(np.mean(values)), "median": float(np.median(values)),
                   "std": float(np.std(values)), "p25": float(np.percentile(values, 25)),
                   "p75": float(np.percentile(values, 75))} for ref, values in distributions.items()}
    clusters, representatives, outliers = [], [], []
    common = sorted(set.intersection(*(set(v) for v in vectors))) if vectors else []
    if completed:
        # Common scalar features, z-scored across this collection; no imputation of failed measurements.
        matrix = np.array([[v[key] for key in common] for v in vectors], dtype=float)
        if common:
            std = matrix.std(axis=0)
            matrix = (matrix - matrix.mean(axis=0)) / np.where(std > 0, std, 1)
            matrix /= math.sqrt(len(common))
        else:
            matrix = np.zeros((len(completed), 1))
        labels = (fcluster(linkage(pdist(matrix), method="average"), t=1.0, criterion="distance")
                  if len(completed) > 1 and common else np.ones(len(completed), dtype=int))
        distances = np.linalg.norm(matrix - matrix.mean(axis=0), axis=1)
        q1, q3 = np.percentile(distances, [25, 75])
        for label in sorted(set(labels)):
            indices = np.flatnonzero(labels == label)
            medoid = indices[int(np.argmin(cdist(matrix[indices], matrix[indices]).sum(axis=1)))]
            representative = str(completed[medoid][0].id)
            representatives.append(representative)
            clusters.append({"cluster_id": int(label), "item_ids": [str(completed[i][0].id) for i in indices],
                             "representative_item_id": representative})
        outliers = [{"item_id": str(completed[i][0].id), "distance": float(distance)}
                    for i, distance in enumerate(distances) if distance > q3 + 1.5 * (q3 - q1)]
    return {"completed_count": len(completed), "failed_count": sum(i.status == "failed" for i in items),
            "feature_statistics": stats, "tag_frequency": dict(tags),
            "dimension_summary": dict(semantics), "provenance_modes": dict(modes),
            "clusters": clusters, "representative_item_ids": representatives, "outlier_items": outliers,
            "clustering": {"method": "average linkage on standardized shared scalar features",
                           "distance_cutoff": 1.0, "feature_refs": common,
                           "outlier_rule": "distance to collection centroid > Q3 + 1.5 IQR",
                           "status": "computed" if common else "insufficient_features"},
            "summary": f"{len(completed)} of {len(items)} images produced results. "
                       f"{len(clusters)} feature groups; {len(outliers)} statistical outliers. "
                       f"Frequent tags: {', '.join(tag for tag, _ in tags.most_common()) or 'none'}."}
