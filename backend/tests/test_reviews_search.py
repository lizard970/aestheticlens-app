from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.models import AnalysisJob, AnalysisResult, AnalysisTarget, Asset, DimensionResult, FeatureResult
from app.repositories import InMemoryRepository
from app.reviews import ReviewService
from app.evidence import resolve_evidence


REF = "feature:cie_lightness#/mean"


@pytest.fixture
def stored(monkeypatch):
    repository = InMemoryRepository()
    monkeypatch.setattr(main, "repository", repository)
    asset = Asset(original_filename="case.png", mime_type="image/png", size_bytes=7)
    repository.assets[asset.id] = asset
    repository.asset_bytes[asset.id] = b"fixture"
    job = AnalysisJob(target=AnalysisTarget(type="asset", id=asset.id), analysis_profile_id="aesthetic-core-v1", requested_outputs=["features", "aesthetic_analysis"])
    repository.jobs[job.id] = job
    result = AnalysisResult(job_id=job.id, summary="Stored test case", tags=["minimalist", "retro_treatment"],
        dimensions=[DimensionResult(code=code, label=code, observation="Original observation", interpretation="Original interpretation",
                                    confidence=0.5, evidence_refs=[REF]) for code in ["composition", "color", "lighting", "space", "style"]],
        features=[FeatureResult(extractor_code="cie_lightness", extractor_version="1", feature_schema_version="1", method="Lightness", status="succeeded",
                                values={"mean": 0.5, "flag": True, "text": "0.5", "a/b~c": [0.25]})],
        provenance={"mode": "real", "semantic": {"status": "succeeded"}})
    repository.results[job.id] = result
    return repository, result, TestClient(main.app)


def save(client, result, code, kind="accept", **kwargs):
    return client.post(f"/api/v1/analysis-results/{result.id}/feedback", json={
        "feedback_type": kind, "target_path": f"/dimensions/{code}", **kwargs})


def confirm(client, result):
    for dimension in result.dimensions:
        assert save(client, result, dimension.code).status_code == 201


def search(client, **kwargs):
    return client.post("/api/v1/search/structured", json=kwargs)


def test_evidence_resolves_stored_values_deduplicates_and_marks_invalid(stored):
    _, result, client = stored
    result.dimensions[0].evidence_refs += ["feature:cie_lightness#/a~1b~0c/0", "feature:missing#/value", "mock:style"]
    evidence = {item.id: item for item in resolve_evidence(result)}
    assert evidence[REF].label == "平均感知明度 L*"
    assert evidence[REF].value == 0.5
    assert len(evidence[REF].supports_dimensions) == 5
    assert evidence["feature:cie_lightness#/a~1b~0c/0"].value == 0.25
    assert evidence["feature:missing#/value"].status == "invalid"
    assert evidence["mock:style"].status == "mock"
    response = client.get(f"/api/v1/analysis-jobs/{result.job_id}/result")
    assert response.status_code == 200
    assert response.json()["evidence"][0]["value"] == 0.5
    assert all("region" not in item for item in response.json()["evidence"])


def test_edit_history_recovery_and_raw_output_immutability(stored):
    repository, result, client = stored
    raw = result.model_dump(mode="json")
    corrected = {"observation": "Human observation", "interpretation": "Human interpretation"}
    first = save(client, result, "composition", "edit", corrected_value=corrected,
                 comment="review note", error_category="attribute_error", base_revision=0)
    assert first.status_code == 201
    assert first.json()["original_value"]["observation"] == "Original observation"
    assert first.json()["revision"] == 1
    assert save(client, result, "composition", "reject", base_revision=1).status_code == 201
    history = client.get(f"/api/v1/analysis-results/{result.id}/feedback").json()
    assert history["original_result"] == raw
    assert len(history["feedback"]) == 2
    assert [item["revision"] for item in history["feedback"]] == [2, 1]
    assert history["latest_revision"]["dimensions"][0]["review_status"] == "reject"
    previous = client.get(f"/api/v1/analysis-results/{result.id}?revision=1").json()
    assert previous["human_revision"]["dimensions"][0]["observation"] == "Human observation"
    assert previous["dimensions"][0]["observation"] == "Original observation"
    assert client.get(f"/api/v1/analysis-results/{result.id}?revision=0").json()["human_revision"]["dimensions"][0]["review_status"] == "unreviewed"
    assert client.get(f"/api/v1/analysis-results/{result.id}?revision=99").status_code == 404
    restored = ReviewService(repository).view(result.id)
    assert restored.human_revision.revision == 2
    assert restored.human_revision.dimensions[0].interpretation == "Human interpretation"
    assert repository.results[result.job_id].model_dump(mode="json") == raw
    restored.dimensions[0].observation = "mutated client copy"
    assert repository.results[result.job_id].model_dump(mode="json") == raw
    assert client.get("/api/v1/analysis-results").json()["items"][0]["id"] == str(result.id)
    assert client.get(restored.preview_url).content == b"fixture"


@pytest.mark.parametrize("kind", ["accept", "edit", "reject"])
@pytest.mark.parametrize("comment", ["review comment", None])
def test_every_review_action_persists_explicit_optional_comment(stored, kind, comment):
    repository, result, client = stored
    extra = {"corrected_value": {"observation": "Human", "interpretation": "Edited"}} if kind == "edit" else {}
    response = save(client, result, "color", kind, comment=comment, **extra)
    assert response.status_code == 201
    assert response.json()["comment"] == comment
    assert repository.read_feedback(result.id)[0].comment == comment
    history = client.get(f"/api/v1/analysis-results/{result.id}/feedback").json()["feedback"]
    assert history[0]["comment"] == comment


def test_dimension_targets_remain_separate_in_history(stored):
    _, result, client = stored
    for dimension in result.dimensions:
        assert save(client, result, dimension.code, comment=f"note-{dimension.code}").status_code == 201
    payload = client.get(f"/api/v1/analysis-results/{result.id}").json()
    assert len(payload["feedback_history"]) == 5
    for dimension in result.dimensions:
        prefix = f"/dimensions/{dimension.code}"
        targeted = [item for item in payload["feedback_history"] if item["target_path"] == prefix or item["target_path"].startswith(prefix + "/")]
        assert len(targeted) == 1


def test_field_edits_compose_and_conflicts_do_not_append(stored):
    _, result, client = stored
    for field, value in [("observation", "New observation"), ("interpretation", "New interpretation")]:
        response = client.post(f"/api/v1/analysis-results/{result.id}/feedback", json={
            "feedback_type": "edit", "target_path": f"/dimensions/color/{field}", "corrected_value": value})
        assert response.status_code == 201
    assert save(client, result, "color", base_revision=0).status_code == 409
    revision = client.get(f"/api/v1/analysis-results/{result.id}").json()["human_revision"]
    assert revision["revision"] == 2
    assert revision["dimensions"][1]["observation"] == "New observation"
    assert revision["dimensions"][1]["interpretation"] == "New interpretation"


@pytest.mark.parametrize("payload", [
    {"feedback_type": "edit", "target_path": "/dimensions/nope", "corrected_value": "bad"},
    {"feedback_type": "edit", "target_path": "/dimensions/color", "corrected_value": {"observation": "missing interpretation"}},
    {"feedback_type": "edit", "target_path": "/dimensions/color/tags", "corrected_value": "bad"},
    {"feedback_type": "accept", "target_path": "/dimensions/color", "corrected_value": "bad"},
])
def test_invalid_feedback_is_rejected(stored, payload):
    repository, result, client = stored
    assert client.post(f"/api/v1/analysis-results/{result.id}/feedback", json=payload).status_code == 422
    assert repository.read_feedback(result.id) == []
    assert client.get(f"/api/v1/analysis-results/{uuid4()}/feedback").status_code == 404


@pytest.mark.parametrize("op,value,matched", [("eq", 0.5, True), ("gt", 0.5, False), ("gte", 0.5, True),
                                            ("lt", 0.5, False), ("lte", 0.5, True), ("gt", 0.4, True), ("lt", 0.6, True)])
def test_numeric_operators_and_confirmed_gate(stored, op, value, matched):
    _, result, client = stored
    assert search(client).json()["items"] == []
    confirm(client, result)
    response = search(client, tags=["minimalist"], numeric_filters=[{"feature_ref": REF, "op": op, "value": value}])
    assert response.status_code == 200
    assert bool(response.json()["items"]) is matched


def test_search_and_excludes_rejects_mock_failed_missing_and_nonnumeric(stored):
    repository, result, client = stored
    confirm(client, result)
    assert search(client, tags=["minimalist", "missing"]).json()["items"] == []
    assert search(client, numeric_filters=[{"feature_ref": REF, "op": "gte", "value": 0.5}, {"feature_ref": REF, "op": "lt", "value": 0.5}]).json()["items"] == []
    for field in ["flag", "text", "missing"]:
        assert search(client, numeric_filters=[{"feature_ref": f"feature:cie_lightness#/{field}", "op": "gte", "value": 0}]).json()["items"] == []
    save(client, result, "style", "reject")
    assert search(client).json()["items"] == []
    save(client, result, "style", "edit", corrected_value={"observation": "Confirmed", "interpretation": "Revised style"})
    hit = search(client).json()["items"][0]
    assert hit["result_id"] == str(result.id)
    assert hit["revision"] == 7
    assert hit["preview_text"] == "Original observation"
    assert client.get(f"/api/v1/analysis-results/{result.id}").json()["human_revision"]["dimensions"][-1]["interpretation"] == "Revised style"
    result.provenance["mode"] = "hybrid"
    assert search(client).json()["items"] == []
    result.provenance["mode"] = "real"
    result.provenance["semantic"]["status"] = "failed"
    assert search(client).json()["items"] == []
    result.provenance["semantic"]["status"] = "succeeded"
    result.features[0].status = "failed"
    assert search(client).json()["items"] == []
    result.features[0].status = "succeeded"
    result.dimensions[0].evidence_refs = ["feature:missing#/value"]
    assert search(client).json()["items"] == []
    assert repository.results[result.job_id] is result


def test_search_input_validation_and_capabilities(stored):
    _, _, client = stored
    for condition in [{"feature_ref": REF, "op": "between", "value": 0.5},
                      {"feature_ref": "invalid", "op": "eq", "value": 0.5},
                      {"feature_ref": REF, "op": "eq", "value": True},
                      {"feature_ref": REF, "op": "eq", "value": "0.5"}]:
        assert search(client, numeric_filters=[condition]).status_code == 422
    assert search(client, semantic_query="unsupported").status_code == 422
    codes = {item["code"]: item["status"] for item in client.get("/api/v1/capabilities").json()["capabilities"]}
    assert codes["structured_search"] == "available"
    assert codes["semantic_search"] == "available"
    assert codes["hybrid_search"] == "available"
