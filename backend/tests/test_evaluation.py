import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.evaluation import (EvaluationCaseCreate, EvaluationFeedbackCreate, EvaluationService,
                            approval_rate, modification_rate, rejection_rate, average_revision_count)
from app.models import Asset
from app.repositories import InMemoryRepository, PostgreSQLRepository


def setup_case(repo):
    asset = Asset(original_filename="evaluation.png", mime_type="image/png", size_bytes=1)
    repo.save_asset(asset, b"x")
    service = EvaluationService(repo)
    case = service.create_case(EvaluationCaseCreate(asset_id=asset.id, category="lighting"))
    return service, case


def test_http_cases_feedback_and_validation(monkeypatch):
    repo = InMemoryRepository()
    monkeypatch.setattr(main, "repository", repo)
    service, case = setup_case(repo)
    client = TestClient(main.app)
    response = client.post("/api/v1/evaluation/cases", json={"asset_id": str(case.asset_id),
        "category": "style", "expected_tags": ["cinematic"], "evaluator_notes": "Check shadows"})
    assert response.status_code == 201
    assert response.json()["expected_tags"] == ["cinematic"]
    assert response.json()["evaluator_notes"] == "Check shadows"
    assert len(client.get("/api/v1/evaluation/cases").json()) == 2
    run = service.record_run(case.id, {"summary": "unaltered"})
    for decision in ("approved", "modified", "rejected"):
        response = client.post("/api/v1/evaluation/feedback", json={"run_id": str(run.id),
            "decision": decision, "revision_count": 2, "error_categories": ["tag"], "comments": "human note"})
        assert response.status_code == 201
        assert response.json()["comments"] == "human note"
        assert response.json()["decision"] == decision
    assert len(repo.list_evaluation_feedback(run.id)) == 3
    assert repo.get_evaluation_run(run.id).model_output == {"summary": "unaltered"}
    assert repo.results == {} and repo.feedback == {}  # No production analysis or review writes.
    assert client.post("/api/v1/evaluation/feedback", json={"run_id": str(uuid4()),
        "decision": "approved"}).status_code == 404
    assert client.post("/api/v1/evaluation/cases", json={"asset_id": str(uuid4()),
        "category": "style"}).status_code == 404
    for invalid in ({"decision": "accept"}, {"revision_count": -1}, {"revision_count": 1.5}):
        assert client.post("/api/v1/evaluation/feedback", json={"run_id": str(run.id),
            "decision": "approved", **invalid}).status_code == 422


def test_snapshot_isolation_append_only_and_optional_fields():
    repo = InMemoryRepository()
    service, case = setup_case(repo)
    assert case.expected_tags is None
    output = {"tags": ["original"]}
    run = service.record_run(case.id, output)
    output["tags"].append("later")
    run.model_output["tags"].append("also later")
    assert repo.get_evaluation_run(run.id).model_output == {"tags": ["original"]}
    with pytest.raises(ValueError, match="EXISTS"):
        repo.save_evaluation_run(run)
    with pytest.raises(LookupError):
        service.record_run(uuid4(), {})
    for comment in (None, ""):
        feedback = service.submit_feedback(EvaluationFeedbackCreate(run_id=run.id,
            decision="approved", comments=comment))
        assert feedback.comments == comment
        assert feedback.error_categories == []
    other = service.record_run(case.id, "text output")
    assert repo.list_evaluation_feedback(other.id) == []


def test_metrics_describe_feedback_not_automatic_scores():
    rows = [EvaluationFeedbackCreate(run_id=uuid4(), decision=d, revision_count=n)
            for d, n in [("approved", 0), ("approved", 0), ("modified", 3), ("rejected", 1)]]
    for metric, expected in [(approval_rate, .5), (modification_rate, .25),
                             (rejection_rate, .25), (average_revision_count, 1.0)]:
        assert metric(iter(rows)) == expected
        assert metric([]) == 0.0


@pytest.mark.skipif(not os.getenv("AESTHETICLENS_TEST_DATABASE_URL"), reason="PostgreSQL test URL not configured")
def test_postgresql_evaluation_restart():
    url = os.environ["AESTHETICLENS_TEST_DATABASE_URL"]
    repo = PostgreSQLRepository(url)
    repo.migrate()
    service, case = setup_case(repo)
    run = service.record_run(case.id, {"summary": "snapshot"})
    feedback = service.submit_feedback(EvaluationFeedbackCreate(run_id=run.id,
        decision="modified", revision_count=2, error_categories=["style"], comments="correction"))
    restarted = PostgreSQLRepository(url)
    assert restarted.get_evaluation_case(case.id) == case
    assert case in restarted.list_evaluation_cases()
    assert restarted.get_evaluation_run(run.id) == run
    assert restarted.list_evaluation_feedback(run.id) == [feedback]
