from uuid import uuid4

import pytest
import httpx
from fastapi.testclient import TestClient

import app.main as main
from app.knowledge import SemanticSearchService
from app.embeddings import EMBEDDING_DIMENSIONS, OpenAIEmbeddingAdapter, OpenAIEmbeddingSettings
from app.models import (AnalysisJob, AnalysisResult, AnalysisTarget, Asset, DimensionResult,
                        FeatureResult, FeedbackCreate, SemanticSearchRequest)
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


def add_case(repository, interpretation="quiet cold image", mode="real"):
    asset = Asset(original_filename=f"{uuid4()}.png", mime_type="image/png", size_bytes=1)
    job = AnalysisJob(target=AnalysisTarget(type="asset", id=asset.id), analysis_profile_id="aesthetic-core-v1",
                      requested_outputs=["features"])
    dimensions = [DimensionResult(code=code, label=code, observation="Observation",
                                  interpretation=f"{interpretation} {code}", confidence=.5, evidence_refs=[])
                  for code in ["composition", "color", "lighting", "space", "style"]]
    result = AnalysisResult(job_id=job.id, summary=interpretation, dimensions=dimensions, tags=["restrained"],
                            provenance={"mode": mode, "semantic": {"status": "succeeded"}},
                            features=[FeatureResult(extractor_code="metric", extractor_version="1",
                                                   feature_schema_version="1", method="Metric", status="succeeded",
                                                   values={"secret_feature_json": 123})])
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
