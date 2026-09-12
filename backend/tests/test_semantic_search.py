from uuid import uuid4

import pytest
import httpx
from fastapi.testclient import TestClient

import app.main as main
from app.knowledge import HybridSearchService, SemanticSearchService
from app.embeddings import EMBEDDING_DIMENSIONS, OpenAIEmbeddingAdapter, OpenAIEmbeddingSettings
from app.models import (AnalysisJob, AnalysisResult, AnalysisTarget, Asset, DimensionResult,
                        FeatureResult, FeedbackCreate, HybridSearchRequest, SemanticSearchRequest)
from app.repositories import InMemoryRepository
from app.reviews import ReviewService


class FakeEmbeddingAdapter:
    model_name = "fake-embedding-v1"

    def __init__(self):
        self.inputs = []

    def embed(self, text):
        self.inputs.append(text)
        return [1.0, 0.0] if "cold" in text or "冷" in text else [0.0, 1.0]


def test_openai_adapter_uses_embeddings_api_contract(monkeypatch):
    request = {}

    def respond(url, **kwargs):
        request.update(url=url, **kwargs)
        return httpx.Response(200, json={"data": [{"embedding": [0.0] * EMBEDDING_DIMENSIONS}]},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", respond)
    adapter = OpenAIEmbeddingAdapter(OpenAIEmbeddingSettings(api_key="test-only"))
    assert len(adapter.embed("query")) == EMBEDDING_DIMENSIONS
    assert request["url"].endswith("/embeddings")
    assert request["json"] == {"input": "query", "model": "text-embedding-3-small",
                               "encoding_format": "float", "dimensions": EMBEDDING_DIMENSIONS}


def add_case(repository, interpretation="quiet cold image", mode="real", tags=None, shadow=.5):
    asset = Asset(original_filename=f"{uuid4()}.png", mime_type="image/png", size_bytes=1)
    job = AnalysisJob(target=AnalysisTarget(type="asset", id=asset.id), analysis_profile_id="aesthetic-core-v1",
                      requested_outputs=["features"])
    dimensions = [DimensionResult(code=code, label=code, observation="Observation",
                                  interpretation=f"{interpretation} {code}", confidence=.5, evidence_refs=[])
                  for code in ["composition", "color", "lighting", "space", "style"]]
    result = AnalysisResult(job_id=job.id, summary=interpretation, dimensions=dimensions,
                            tags=tags or ["restrained"],
                            provenance={"mode": mode, "semantic": {"status": "succeeded"}},
                            features=[FeatureResult(extractor_code="tonal_occupancy", extractor_version="1",
                                                   feature_schema_version="1", method="Metric", status="succeeded",
                                                   values={"shadow_share": shadow, "secret_feature_json": 123})])
    repository.save_asset(asset, b"x")
    repository.save_job(job)
    repository.save_result(result)
    return result


def confirm(service, result):
    for index, dimension in enumerate(result.dimensions):
        service.save(result.id, FeedbackCreate(feedback_type="accept", target_path=f"/dimensions/{dimension.code}",
                                               base_revision=index))


def test_only_confirmed_case_gets_embedding_and_reject_removes_it():
    repository = InMemoryRepository()
    adapter = FakeEmbeddingAdapter()
    semantic = SemanticSearchService(repository, adapter)
    reviews = ReviewService(repository, semantic)
    result = add_case(repository)
    semantic.refresh(result.id)
    assert repository.get_case_embedding(result.id) is None
    confirm(reviews, result)
    assert repository.get_case_embedding(result.id) is not None
    reviews.save(result.id, FeedbackCreate(feedback_type="reject", target_path="/dimensions/style", base_revision=5))
    assert repository.get_case_embedding(result.id) is None
    mock = add_case(repository, mode="hybrid")
    confirm(reviews, mock)
    assert repository.get_case_embedding(mock.id) is None


def test_human_tags_reindex_and_case_exclusion_applies_to_all_searches():
    repository = InMemoryRepository()
    adapter = FakeEmbeddingAdapter()
    semantic = SemanticSearchService(repository, adapter)
    reviews = ReviewService(repository, semantic)
    result = add_case(repository)
    confirm(reviews, result)
    reviews.save(result.id, FeedbackCreate(feedback_type="edit", target_path="/dimensions/style", base_revision=5,
        corrected_value={"observation": "Human", "interpretation": "Human", "tags": ["human-tag"]}))
    assert "Style tags: human-tag" in adapter.inputs[-1]
    assert "restrained" not in adapter.inputs[-1]
    assert HybridSearchService(repository, adapter).search(HybridSearchRequest(tags=["human-tag"]))[0].tags == ["human-tag"]
    reviews.save(result.id, FeedbackCreate(feedback_type="edit", target_path="/knowledge_excluded", corrected_value=True, base_revision=6))
    assert repository.get_case_embedding(result.id) is None
    assert semantic.search(SemanticSearchRequest(query="cold")) == []
    assert HybridSearchService(repository, adapter).search(HybridSearchRequest(query="cold")) == []


def test_edited_human_interpretation_is_embedded_instead_of_raw_text():
    repository = InMemoryRepository()
    adapter = FakeEmbeddingAdapter()
    reviews = ReviewService(repository, SemanticSearchService(repository, adapter))
    result = add_case(repository, interpretation="raw warm model text")
    for index, dimension in enumerate(result.dimensions[:-1]):
        reviews.save(result.id, FeedbackCreate(feedback_type="accept", target_path=f"/dimensions/{dimension.code}",
                                               base_revision=index))
    reviews.save(result.id, FeedbackCreate(
        feedback_type="edit", target_path="/dimensions/style", base_revision=4,
        corrected_value={"observation": "Human observation", "interpretation": "human quiet cold edit"},
    ))
    stored = repository.get_case_embedding(result.id)
    assert stored is not None
    assert "human quiet cold edit" in stored.source_text
    assert "raw warm model text style" not in stored.source_text
    assert "secret_feature_json" not in stored.source_text


def test_semantic_query_returns_nearest_stored_cases_and_api_shape(monkeypatch):
    repository = InMemoryRepository()
    adapter = FakeEmbeddingAdapter()
    semantic = SemanticSearchService(repository, adapter)
    reviews = ReviewService(repository, semantic)
    cold = add_case(repository, "quiet cold")
    warm = add_case(repository, "bright warm")
    confirm(reviews, cold)
    confirm(reviews, warm)
    matches = semantic.search(SemanticSearchRequest(query="安静、克制、偏冷的画面", limit=1))
    assert [item.result_id for item in matches] == [cold.id]
    assert matches[0].similarity == pytest.approx(1.0)

    monkeypatch.setattr(main, "semantic_search_service", semantic)
    response = TestClient(main.app).post("/api/v1/search/semantic", json={"query": "偏冷", "limit": 1})
    assert response.status_code == 200
    assert response.json()["items"][0]["result_id"] == str(cold.id)
    assert set(response.json()["items"][0]) == {
        "asset_id", "result_id", "similarity", "tags", "original_filename",
        "preview_url", "revision", "preview_text",
    }


def test_hybrid_endpoint_supports_semantic_only(monkeypatch):
    repository = InMemoryRepository()
    adapter = FakeEmbeddingAdapter()
    semantic = SemanticSearchService(repository, adapter)
    reviews = ReviewService(repository, semantic)
    cold = add_case(repository, "quiet cold")
    warm = add_case(repository, "bright warm")
    confirm(reviews, cold)
    confirm(reviews, warm)
    hybrid = HybridSearchService(repository, adapter)
    monkeypatch.setattr(main, "hybrid_search_service", hybrid)
    response = TestClient(main.app).post("/api/v1/search/hybrid", json={"query": "偏冷", "limit": 1})
    assert response.status_code == 200
    assert response.json()["items"][0]["result_id"] == str(cold.id)
    assert response.json()["items"][0]["matched_structured_conditions"] == {
        "tags": [], "numeric_filters": [],
    }


def test_hybrid_structured_only_uses_hard_and_filters_without_embedding_query(monkeypatch):
    repository = InMemoryRepository()
    reviews = ReviewService(repository)
    match = add_case(repository, tags=["cinematic", "restrained"], shadow=.6)
    wrong_tag = add_case(repository, tags=["restrained"], shadow=.8)
    too_light = add_case(repository, tags=["cinematic"], shadow=.2)
    for result in [match, wrong_tag, too_light]:
        confirm(reviews, result)
    request = HybridSearchRequest(tags=["cinematic"], numeric_filters=[
        {"field": "shadow_occupancy", "op": "gte", "value": .4},
    ], limit=10)
    hybrid = HybridSearchService(repository, None)
    matches = hybrid.search(request)
    assert [item.result_id for item in matches] == [match.id]
    assert matches[0].similarity is None
    assert matches[0].matched_structured_conditions.model_dump() == request.model_dump(exclude={"query", "limit"})
    monkeypatch.setattr(main, "hybrid_search_service", hybrid)
    response = TestClient(main.app).post("/api/v1/search/hybrid", json=request.model_dump())
    assert response.status_code == 200
    assert [item["result_id"] for item in response.json()["items"]] == [str(match.id)]


def test_hybrid_filters_before_semantic_ranking_and_excludes_invalid_candidates(monkeypatch):
    repository = InMemoryRepository()
    adapter = FakeEmbeddingAdapter()
    semantic = SemanticSearchService(repository, adapter)
    reviews = ReviewService(repository, semantic)
    similar_but_filtered = add_case(repository, "quiet cold", tags=["cinematic"], shadow=.2)
    eligible_but_distant = add_case(repository, "bright warm", tags=["cinematic"], shadow=.8)
    unconfirmed = add_case(repository, "quiet cold", tags=["cinematic"], shadow=.9)
    confirm(reviews, similar_but_filtered)
    confirm(reviews, eligible_but_distant)
    assert repository.get_case_embedding(unconfirmed.id) is None
    hybrid = HybridSearchService(repository, adapter)
    request = HybridSearchRequest(
        query="偏冷", tags=["cinematic"],
        numeric_filters=[{"field": "shadow_occupancy", "op": "gte", "value": .4}], limit=10,
    )
    matches = hybrid.search(request)
    assert [item.result_id for item in matches] == [eligible_but_distant.id]
    assert matches[0].similarity == pytest.approx(0.0)
    monkeypatch.setattr(main, "hybrid_search_service", hybrid)
    response = TestClient(main.app).post("/api/v1/search/hybrid", json=request.model_dump())
    assert response.status_code == 200
    assert [item["result_id"] for item in response.json()["items"]] == [str(eligible_but_distant.id)]
