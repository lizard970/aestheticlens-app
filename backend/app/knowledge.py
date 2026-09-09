import math
import operator
from typing import Protocol
from uuid import UUID

from .embeddings import EmbeddingAdapter
from .evidence import resolve_evidence
from .models import (AnalysisResult, HumanRevision, SearchableCase, SemanticSearchCase,
                     SemanticSearchRequest, StoredCaseEmbedding, StructuredSearchRequest)
from .repositories import Repository
from .reviews import ReviewService
from .semantic_adapter import feature_evidence


class KnowledgeRepository(Protocol):
    def search(self, query: StructuredSearchRequest) -> list[SearchableCase]: ...


def searchable_revision(repository: Repository, result: AnalysisResult) -> HumanRevision | None:
    if result.provenance.get("mode") != "real" or result.provenance.get("semantic", {}).get("status") != "succeeded":
        return None
    if not result.features or not any(feature.status == "succeeded" for feature in result.features):
        return None
    revision = ReviewService(repository).revision(result.id)
    if not revision.dimensions or any(item.review_status not in {"accept", "edit"} for item in revision.dimensions):
        return None
    if any(item.status != "resolved" for item in resolve_evidence(result)):
        return None
    return revision


class StoredKnowledgeRepository:
    """Read projection over stored results/revisions; replace with SQL behind this boundary."""
    def __init__(self, repository: Repository):
        self.repository = repository

    def search(self, query: StructuredSearchRequest) -> list[SearchableCase]:
        compare = {"eq": operator.eq, "gt": operator.gt, "gte": operator.ge, "lt": operator.lt, "lte": operator.le}
        matches = []
        for result in self.repository.list_results():
            revision = searchable_revision(self.repository, result)
            if revision is None:
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


def embedding_text(result: AnalysisResult, revision: HumanRevision) -> str:
    parts = [f"Summary: {result.summary}"]
    if result.tags:
        parts.append("Style tags: " + ", ".join(result.tags))
    parts.extend(dimension.interpretation for dimension in revision.dimensions)
    return "\n".join(parts)


class SemanticSearchService:
    def __init__(self, repository: Repository, adapter: EmbeddingAdapter) -> None:
        self.repository = repository
        self.adapter = adapter

    def refresh(self, result_id: UUID) -> None:
        result = self.repository.get_result(result_id)
        if result is None:
            raise LookupError("ANALYSIS_RESULT_NOT_FOUND")
        revision = searchable_revision(self.repository, result)
        if revision is None:
            self.repository.delete_case_embedding(result_id)
            return
        source_text = embedding_text(result, revision)
        self.repository.upsert_case_embedding(StoredCaseEmbedding(
            result_id=result.id, revision=revision.revision, model=self.adapter.model_name,
            source_text=source_text, embedding=self.adapter.embed(source_text),
        ))

    def search(self, query: SemanticSearchRequest) -> list[SemanticSearchCase]:
        vector = self.adapter.embed(query.query)
        matches = []
        for stored, similarity in self.repository.search_case_embeddings(vector, query.limit):
            result = self.repository.get_result(stored.result_id)
            if result is None:
                continue
            revision = searchable_revision(self.repository, result)
            if revision is None or revision.revision != stored.revision:
                continue
            job = self.repository.get_job(result.job_id)
            asset = self.repository.get_asset(job.target.id) if job else None
            if asset is None:
                continue
            matches.append(SemanticSearchCase(
                asset_id=asset.id, result_id=result.id, similarity=similarity, tags=result.tags,
                original_filename=asset.original_filename,
                preview_url=f"/api/v1/assets/{asset.id}/content", revision=revision.revision,
                preview_text=revision.dimensions[0].interpretation,
            ))
        return matches
