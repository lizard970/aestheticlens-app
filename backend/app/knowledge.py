import math
import operator
from typing import Protocol

from .evidence import resolve_evidence
from .models import SearchableCase, StructuredSearchRequest
from .repositories import Repository
from .reviews import ReviewService
from .semantic_adapter import feature_evidence


class KnowledgeRepository(Protocol):
    def search(self, query: StructuredSearchRequest) -> list[SearchableCase]: ...


class StoredKnowledgeRepository:
    """Read projection over stored results/revisions; replace with SQL behind this boundary."""
    def __init__(self, repository: Repository):
        self.repository = repository
        self.reviews = ReviewService(repository)

    def search(self, query: StructuredSearchRequest) -> list[SearchableCase]:
        compare = {"eq": operator.eq, "gt": operator.gt, "gte": operator.ge, "lt": operator.lt, "lte": operator.le}
        matches = []
        for result in self.repository.list_results():
            if result.provenance.get("mode") != "real" or result.provenance.get("semantic", {}).get("status") != "succeeded":
                continue
            if not result.features or not any(f.status == "succeeded" for f in result.features):
                continue
            revision = self.reviews.revision(result.id)
            if not revision.dimensions or any(d.review_status not in {"accept", "edit"} for d in revision.dimensions):
                continue
            if any(e.status != "resolved" for e in resolve_evidence(result)):
                continue
            if not set(query.tags).issubset(result.tags):
                continue
            values = feature_evidence(result.features)
            def passes(condition):
                value = values.get(condition.feature_ref)
                return type(value) in {int, float} and math.isfinite(value) and compare[condition.op](value, condition.value)
            if not all(passes(condition) for condition in query.numeric_filters):
                continue
            job = self.repository.get_job(result.job_id)
            asset = self.repository.get_asset(job.target.id) if job else None
            if asset is None:
                continue
            matches.append(SearchableCase(asset_id=asset.id, result_id=result.id, job_id=job.id,
                                          original_filename=asset.original_filename,
                                          preview_url=f"/api/v1/assets/{asset.id}/content", tags=result.tags,
                                          revision=revision.revision, preview_text=revision.dimensions[0].observation))
        return matches
