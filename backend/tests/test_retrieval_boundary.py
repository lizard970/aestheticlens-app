import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.knowledge import HybridSearchService, SemanticSearchService
from app.models import FeedbackCreate, HybridSearchRequest, SemanticSearchRequest
from app.query_understanding import mentions, ENTITIES
from app.repositories import InMemoryRepository
from app.reviews import ReviewService
from test_semantic_search import add_case, confirm, FakeEmbeddingAdapter


@pytest.mark.parametrize("service_type,request_type", [(HybridSearchService, HybridSearchRequest), (SemanticSearchService, SemanticSearchRequest)])
def test_threshold_does_not_fill_limit_and_zero_results(service_type, request_type):
    repository = InMemoryRepository()
    adapter = FakeEmbeddingAdapter()
    reviews = ReviewService(repository, SemanticSearchService(repository, adapter))
    cold, warm = add_case(repository, "cold"), add_case(repository, "warm")
    confirm(reviews, cold)
    confirm(reviews, warm)
    service = service_type(repository, adapter)
    assert [item.result_id for item in service.search(request_type(query="cold", limit=10))] == [cold.id]
    assert len(service.search(request_type(query="cold", limit=10, min_similarity=0))) == 2
    reviews.save(cold.id, FeedbackCreate(feedback_type="reject", target_path="/dimensions/style", base_revision=5))
    assert service.search(request_type(query="cold", limit=10)) == []


def test_entity_hard_filter_before_ranking_and_debug_even_when_empty(monkeypatch):
    repository = InMemoryRepository()
    adapter = FakeEmbeddingAdapter()
    reviews = ReviewService(repository, SemanticSearchService(repository, adapter))
    cat = add_case(repository, "cold 小猫")
    distant_cat = add_case(repository, "warm cat")
    dog = add_case(repository, "cold 小狗")
    for case in [cat, distant_cat, dog]:
        confirm(reviews, case)
    hybrid = HybridSearchService(repository, adapter)
    monkeypatch.setattr(main, "hybrid_search_service", hybrid)
    response = TestClient(main.app).post('/api/v1/search/hybrid', json={"query": "cold 的小猫", "limit": 10, "min_similarity": 0})
    assert response.status_code == 200
    assert [item["result_id"] for item in response.json()["items"]] == [str(cat.id), str(distant_cat.id)]
    assert adapter.inputs[-1] == "cold"
    assert response.json()["applied_filters"]["entities"] == ["cat"]
    assert response.json()["applied_filters"]["reasons"]
    assert [item.similarity for item in hybrid.search(HybridSearchRequest(query="cold 小猫", min_similarity=0))] == [1, 0]
    response = TestClient(main.app).post('/api/v1/search/hybrid', json={"query": "cold 小猫", "tags": ["missing"]})
    assert response.json()["items"] == []
    assert response.json()["applied_filters"]["entities"] == ["cat"]


def test_final_revision_overrides_entity_evidence_and_unknown_is_not_invented():
    repository = InMemoryRepository()
    adapter = FakeEmbeddingAdapter()
    reviews = ReviewService(repository, SemanticSearchService(repository, adapter))
    case = add_case(repository, "cold cat")
    confirm(reviews, case)
    for i, dimension in enumerate(case.dimensions):
        reviews.save(case.id, FeedbackCreate(feedback_type="edit", target_path=f"/dimensions/{dimension.code}", base_revision=5+i,
            corrected_value={"observation": "a dog", "interpretation": "cold dog"}))
    debug = {}
    HybridSearchService(repository, adapter).search(HybridSearchRequest(query="cold cat"), debug)
    assert debug["entities"] == []  # Raw summary still says cat, but does not count.
    assert debug["ranking_query"] == "cold cat"
    assert "no confident" in debug["reasons"][0]


@pytest.mark.parametrize("text", ["没有猫", "可能是小猫", "熊猫", "猫头鹰", "cathedral", "not a cat", "resembles a cat"])
def test_ambiguous_entity_is_not_a_confident_constraint(text):
    assert not mentions(text, ENTITIES['cat'])


def test_entity_only_query_does_not_require_an_embedding_call():
    repository = InMemoryRepository()
    case = add_case(repository, "小猫")
    confirm(ReviewService(repository), case)
    assert HybridSearchService(repository, None).search(HybridSearchRequest(query="小猫"))[0].result_id == case.id
