import json
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.answers import AnswerDraft, AnswerRequest, KnowledgeAnswerService
from app.knowledge import HybridSearchService, SemanticSearchService
from app.models import FeedbackCreate
from app.repositories import InMemoryRepository
from app.reviews import ReviewService
from test_semantic_search import FakeEmbeddingAdapter, add_case, confirm


class RecordingAnswer:
    def __init__(self):
        self.context = None

    def answer(self, question, context):
        self.context = context
        return AnswerDraft(status="answered", answer=context[0]["dimension_interpretations"][0]["interpretation"],
                           cited_case_ids=[context[0]["result_id"]])


def setup():
    repo = InMemoryRepository()
    embedding = FakeEmbeddingAdapter()
    reviews = ReviewService(repo, SemanticSearchService(repo, embedding))
    adapter = RecordingAnswer()
    service = KnowledgeAnswerService(repo, HybridSearchService(repo, embedding), adapter)
    return repo, reviews, adapter, service


def test_answer_uses_retrieved_human_revision_and_exact_citations():
    repo, reviews, adapter, service = setup()
    case = add_case(repo)
    confirm(reviews, case)
    reviews.save(case.id, FeedbackCreate(feedback_type="edit", target_path="/dimensions/composition/interpretation",
                                        corrected_value="human cold interpretation"))
    result = service.answer(AnswerRequest(question="cold"))
    assert result.status == "answered"
    assert result.answer == "human cold interpretation"
    assert result.cited_case_ids == [case.id]
    assert [hit.result_id for hit in result.retrieved_cases] == [case.id]
    assert "secret_feature_json" not in json.dumps(adapter.context)


@pytest.mark.parametrize("state", ["empty", "unconfirmed", "rejected", "mock", "irrelevant", "invalid"])
def test_insufficient_evidence_skips_llm(state):
    repo, reviews, adapter, service = setup()
    if state != "empty":
        case = add_case(repo, interpretation="warm" if state == "irrelevant" else "cold",
                        mode="hybrid" if state == "mock" else "real")
        if state != "unconfirmed":
            confirm(reviews, case)
        if state == "rejected":
            reviews.save(case.id, FeedbackCreate(feedback_type="reject", target_path="/dimensions/style"))
        if state == "invalid":
            repo.results[case.job_id].dimensions[0].evidence_refs = ["feature:missing#/value"]
    result = service.answer(AnswerRequest(question="cold"))
    assert result.status == "insufficient_evidence"
    assert result.cited_case_ids == []
    assert adapter.context is None


def test_unknown_citation_fails_closed():
    repo, reviews, adapter, service = setup()
    confirm(reviews, add_case(repo))
    adapter.answer = lambda *args: AnswerDraft(status="answered", answer="unsupported", cited_case_ids=[uuid4()])
    assert service.answer(AnswerRequest(question="cold")).status == "insufficient_evidence"


def test_endpoint_and_configured_llm_contract(monkeypatch):
    repo, reviews, _, service = setup()
    case = add_case(repo)
    confirm(reviews, case)
    monkeypatch.setattr(main, "repository", repo)
    monkeypatch.setattr(main, "hybrid_search_service", service.retrieval)
    for key, value in {"PROVIDER": "chat_completions", "BASE_URL": "https://example.test/v1",
                       "MODEL": "test-model", "API_KEY": "test-only"}.items():
        monkeypatch.setenv("AESTHETICLENS_" + key, value)
    def post(url, **kwargs):
        payload = kwargs["json"]
        context = json.loads(payload["messages"][1]["content"])["cases"]
        assert context[0]["result_id"] == str(case.id)
        assert "only from" in payload["messages"][0]["content"]
        return httpx.Response(200, request=httpx.Request("POST", url), json={"choices": [{
            "finish_reason": "stop", "message": {"content": json.dumps({"status": "answered",
            "answer": "Grounded answer", "cited_case_ids": [str(case.id)]})}}]})
    monkeypatch.setattr(httpx, "post", post)
    response = TestClient(main.app).post("/api/v1/knowledge/answers", json={"question": "cold", "limit": 5})
    assert response.status_code == 200
    assert response.json()["cited_case_ids"] == [str(case.id)]
    assert TestClient(main.app).post("/api/v1/knowledge/answers", json={"question": " "}).status_code == 422
