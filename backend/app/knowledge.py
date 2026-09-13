import math
import operator
from typing import Protocol
from uuid import UUID

from .embeddings import EmbeddingAdapter, EmbeddingError
from .evidence import resolve_evidence
from .models import (AnalysisResult, HumanRevision, HybridSearchCase, HybridSearchRequest,
                     MatchedStructuredConditions, SearchableCase, SemanticSearchCase,
                     SemanticSearchRequest, StoredCaseEmbedding, StructuredSearchRequest)
from .repositories import Repository
from .reviews import ReviewService
from .query_understanding import reviewed_entities, understand
from .semantic_adapter import feature_evidence


class KnowledgeRepository(Protocol):
    def search(self, query: StructuredSearchRequest) -> list[SearchableCase]: ...


def searchable_revision(repository: Repository, result: AnalysisResult) -> HumanRevision | None:
    if result.provenance.get("mode") != "real" or result.provenance.get("semantic", {}).get("status") != "succeeded":
        return None
    if not result.features or not any(feature.status == "succeeded" for feature in result.features):
        return None
    revision = ReviewService(repository).revision(result.id)
    if revision.knowledge_excluded:
        return None
    if not revision.dimensions or any(item.review_status not in {"accept", "edit"} for item in revision.dimensions):
        return None
    if any(item.status != "resolved" for item in resolve_evidence(result)):
        return None
    return revision


HYBRID_FIELD_ALIASES = {
    "shadow_occupancy": "feature:tonal_occupancy#/shadow_share",
}


def resolve_hybrid_field(values: dict, field: str) -> str | None:
    if field in HYBRID_FIELD_ALIASES:
        return HYBRID_FIELD_ALIASES[field]
    if field.startswith("feature:"):
        return field
    matches = [reference for reference in values if reference.rsplit("/", 1)[-1] == field]
    return matches[0] if len(matches) == 1 else None


def passes_numeric_filters(result: AnalysisResult, filters) -> bool:
    compare = {"eq": operator.eq, "gt": operator.gt, "gte": operator.ge, "lt": operator.lt, "lte": operator.le}
    values = feature_evidence(result.features)
    for condition in filters:
        reference = resolve_hybrid_field(values, condition.field)
        value = values.get(reference) if reference else None
        if type(value) not in {int, float} or not math.isfinite(value) or not compare[condition.op](value, condition.value):
            return False
    return True


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
            if not set(query.tags).issubset(revision.tags if revision.tags is not None else result.tags):
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
                                          preview_url=f"/api/v1/assets/{asset.id}/content", tags=revision.tags if revision.tags is not None else result.tags,
                                          revision=revision.revision, preview_text=revision.dimensions[0].observation))
        return matches


def embedding_text(result: AnalysisResult, revision: HumanRevision) -> str:
    parts = [f"Summary: {result.summary}"]
    tags = revision.tags if revision.tags is not None else result.tags
    if tags:
        parts.append("Style tags: " + ", ".join(tags))
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
            if not math.isfinite(similarity) or similarity < query.min_similarity:
                continue
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
                asset_id=asset.id, result_id=result.id, similarity=similarity, tags=revision.tags if revision.tags is not None else result.tags,
                original_filename=asset.original_filename,
                preview_url=f"/api/v1/assets/{asset.id}/content", revision=revision.revision,
                preview_text=revision.dimensions[0].interpretation,
            ))
        return matches


class HybridSearchService:
    def __init__(self, repository: Repository, adapter: EmbeddingAdapter | None) -> None:
        self.repository = repository
        self.adapter = adapter

    def search(self, query: HybridSearchRequest, debug: dict | None = None) -> list[HybridSearchCase]:
        candidates = {}
        entity_evidence = {}
        for result in self.repository.list_results():
            revision = searchable_revision(self.repository, result)
            if revision is None:
                continue
            entity_evidence[result.id] = reviewed_entities(result, revision)
            if not set(query.tags).issubset(revision.tags if revision.tags is not None else result.tags):
                continue
            if not passes_numeric_filters(result, query.numeric_filters):
                continue
            job = self.repository.get_job(result.job_id)
            asset = self.repository.get_asset(job.target.id) if job else None
            if asset is not None:
                candidates[result.id] = (result, revision, asset)

        plan = understand(query.query, set().union(*entity_evidence.values()) if entity_evidence else set())
        candidates = {key: value for key, value in candidates.items()
                      if set(plan["entities"]).issubset(entity_evidence[key])}
        if debug is not None:
            debug.update(plan, min_similarity=query.min_similarity, limit=query.limit,
                         tags=query.tags, numeric_filters=[f.model_dump() for f in query.numeric_filters])
        if plan["ranking_query"] is not None:
            if self.adapter is None:
                raise EmbeddingError("SEMANTIC_SEARCH_NOT_CONFIGURED")
            if not candidates:
                return []
            ranked = self.repository.search_case_embeddings(
                self.adapter.embed(plan["ranking_query"]), query.limit, list(candidates)
            )
            ordered = [(stored.result_id, similarity, stored.revision) for stored, similarity in ranked]
        else:
            ordered = [(result_id, None, candidates[result_id][1].revision)
                       for result_id in list(candidates)[:query.limit]]

        conditions = MatchedStructuredConditions(tags=query.tags, numeric_filters=query.numeric_filters, entities=plan["entities"])
        matches = []
        for result_id, similarity, stored_revision in ordered:
            if similarity is not None and (not math.isfinite(similarity) or similarity < query.min_similarity):
                continue
            candidate = candidates.get(result_id)
            if candidate is None:
                continue
            result, revision, asset = candidate
            if revision.revision != stored_revision:
                continue
            matches.append(HybridSearchCase(
                asset_id=asset.id, result_id=result.id, similarity=similarity, tags=revision.tags if revision.tags is not None else result.tags,
                matched_structured_conditions=conditions,
                original_filename=asset.original_filename,
                preview_url=f"/api/v1/assets/{asset.id}/content", revision=revision.revision,
                preview_text=revision.dimensions[0].interpretation,
            ))
        return matches
