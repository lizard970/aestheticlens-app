from io import BytesIO
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app.main as main
from app.models import FeatureResult
from app.repositories import InMemoryRepository
from app.semantic_adapter import MockAnalysisAdapter, SemanticFailure
from app.services import MockAnalysisService


@pytest.mark.parametrize("code", ["MODEL_HTTP_429", "MODEL_HTTP_401"])
def test_retry_reuses_durable_features_and_preserves_previous_attempt(monkeypatch, code):
    repo = InMemoryRepository()
    feature = FeatureResult(extractor_code="test", extractor_version="1", feature_schema_version="1", method="test", status="succeeded", values={"value": 42})
    registry = Mock()
    registry.run.return_value = [feature]
    adapter = Mock()
    adapter.analyze.side_effect = SemanticFailure(code, {"status": "failed"})
    service = MockAnalysisService(repo, registry, adapter)
    monkeypatch.setattr(main, "repository", repo)
    monkeypatch.setattr(main, "analysis_service", service)
    client = TestClient(main.app)
    stream = BytesIO()
    Image.new("RGB", (8, 8), "gray").save(stream, format="PNG")
    asset = client.post("/api/v1/assets", files={"file": ("test.png", stream.getvalue(), "image/png")}).json()
    request = {"target": {"type": "asset", "id": asset["id"]}, "analysis_profile_id": "aesthetic-core-v1", "requested_outputs": ["features", "aesthetic_analysis", "evidence"]}
    first = client.post("/api/v1/analysis-jobs", json=request).json()
    original = client.get(f"/api/v1/analysis-jobs/{first['id']}/result").json()
    assert original["provenance"]["feature_analysis_status"] == "completed"
    assert original["provenance"]["semantic_analysis_status"] == "failed"
    assert original["provenance"]["semantic_error_message"] == code
    assert first["status"] == "partial" and first["progress_stage"] == "semantic_failed"
    assert registry.run.call_count == 1

    def succeed(image, features, profile):
        checkpoint = repo.list_results()[-1]
        assert checkpoint.features == [feature]
        assert checkpoint.provenance["semantic_analysis_status"] == "processing"
        assert repo.get_job(checkpoint.job_id).progress_stage == "analyzing"
        return MockAnalysisAdapter().analyze(image, features, profile)

    adapter.analyze.side_effect = succeed
    # New service instance reads the persisted checkpoint, not an in-process feature cache.
    monkeypatch.setattr(main, "analysis_service", MockAnalysisService(repo, registry, adapter))
    key = str(uuid4())
    second = client.post("/api/v1/analysis-jobs", json=request, headers={"Idempotency-Key": key}).json()
    final = client.get(f"/api/v1/analysis-jobs/{second['id']}/result").json()
    assert second["id"] == key
    assert registry.run.call_count == 1 and adapter.analyze.call_count == 2
    assert final["features"] == original["features"]
    assert final["provenance"]["feature_analysis_status"] == "completed"
    assert final["provenance"]["semantic_analysis_status"] == "completed"
    assert final["provenance"]["semantic_error_message"] is None
    assert final["provenance"]["reused_feature_result_id"] == original["id"]
    assert client.get(f"/api/v1/analysis-results/{original['id']}").json() == original
    assert client.post("/api/v1/analysis-jobs", json=request, headers={"Idempotency-Key": key}).json()["id"] == key
    assert adapter.analyze.call_count == 2
