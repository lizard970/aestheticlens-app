import base64
import json
from io import BytesIO

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app.main as main
from app.config import load_analysis_profiles, load_feature_config
from app.feature_pipeline import normalize_image
from app.models import FeatureResult
from app.semantic_adapter import (
    ChatCompletionsAdapter,
    SemanticFailure,
    SemanticSettings,
    feature_evidence,
    semantic_feature_evidence,
    semantic_numeric_payload,
)
from app.services import MockAnalysisService


PROFILE = load_analysis_profiles()["aesthetic-core-v1"]
REF = "feature:cie_lightness#/mean"


def png():
    stream = BytesIO()
    Image.new("RGB", (16, 12), (128, 128, 128)).save(stream, format="PNG")
    return stream.getvalue()


def inputs():
    image = normalize_image(png(), load_feature_config())
    feature = FeatureResult(extractor_code="cie_lightness", extractor_version="1",
                            feature_schema_version="1", method="fixture", status="succeeded",
                            values={"mean": 53.585})
    return image, [feature], PROFILE


def output():
    return {"schema_version": "1.0.0", "summary": "画面已分析。", "tags": [],
            "dimensions": [{"code": d.code, "observation": "可见灰色画面。",
                            "interpretation": "明度为 {{" + REF + "}}。",
                            "confidence": 0.5, "evidence_refs": [REF],
                            "uncertainty": "单一画面不足以可靠判断风格。" if d.code == "style" else None}
                           for d in PROFILE.dimensions]}


def response(payload=None):
    return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {
        "content": json.dumps(payload if payload is not None else output())}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}})


def adapter(handler, **kwargs):
    settings = SemanticSettings(provider="chat_completions", base_url="https://fixture.invalid/v1",
                                model="fixture-model", api_key="fixture-secret", retry_delay_seconds=0, **kwargs)
    return ChatCompletionsAdapter(settings, httpx.MockTransport(handler))


def test_success_sends_normalized_image_features_schema_and_keeps_usage():
    image, features, profile = inputs()
    failed = features[0].model_copy(update={"extractor_code": "failed_feature", "status": "failed"})

    def handler(request):
        body = json.loads(request.content)
        assert request.url.path == "/v1/chat/completions"
        content = body["messages"][1]["content"]
        text = json.loads(content[0]["text"])
        assert text["feature_evidence"] == {REF: 53.59}
        assert text["schema"]["additionalProperties"] is False
        raw = base64.b64decode(content[1]["image_url"]["url"].split(",", 1)[1])
        decoded = np.asarray(Image.open(BytesIO(raw)))
        np.testing.assert_array_equal(decoded, np.rint(image.srgb * 255).astype(np.uint8))
        return response()

    result = adapter(handler).analyze(image, features + [failed], profile)
    assert len(result.dimensions) == 5
    assert "53.59" in result.dimensions[0].interpretation
    assert "不确定性" in result.dimensions[-1].interpretation
    assert result.tags == []
    assert result.metadata["usage"]["total_tokens"] == 150
    assert result.metadata["cost"] is None
    assert result.metadata["prompt_version"] == "1.0.0"
    assert "fixture-secret" not in json.dumps(result.metadata)


def test_model_numeric_formatting_does_not_mutate_raw_feature_precision():
    feature = FeatureResult(
        extractor_code="fixture",
        extractor_version="1",
        feature_schema_version="1",
        method="fixture",
        status="succeeded",
        values={
            "shadow_share": 0.12356,
            "continuous_metric": 53.585,
            "sample_count": 17,
        },
    )
    raw = feature_evidence([feature])
    formatted = semantic_feature_evidence(raw)

    assert raw["feature:fixture#/shadow_share"] == 0.12356
    assert raw["feature:fixture#/continuous_metric"] == 53.585
    assert formatted["feature:fixture#/shadow_share"] == 0.124
    assert formatted["feature:fixture#/continuous_metric"] == 53.59
    assert formatted["feature:fixture#/sample_count"] == 17
    assert semantic_numeric_payload({"alpha_coverage": 0.45678, "width": 1920}) == {
        "alpha_coverage": 0.457,
        "width": 1920,
    }


@pytest.mark.parametrize("case", ["json", "schema", "reference", "tag", "duplicate_dimension", "inline_number", "inline_reference"])
def test_invalid_outputs_are_rejected_without_silent_fallback(case):
    data = output()
    if case == "schema":
        data["unexpected"] = True
    elif case == "reference":
        data["dimensions"][0]["evidence_refs"] = ["feature:missing#/value"]
    elif case == "tag":
        data["tags"] = ["invented_style"]
    elif case == "duplicate_dimension":
        data["dimensions"][0]["code"] = "style"
    elif case == "inline_number":
        data["dimensions"][0]["observation"] = "明度为 99。"
    elif case == "inline_reference":
        data["dimensions"][0]["observation"] = "{{feature:cie_lightness#/missing}}"
    replies = []

    def handler(request):
        replies.append(request)
        if case == "json":
            return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": "not-json"}}]})
        return response(data)

    with pytest.raises(SemanticFailure, match="MODEL_OUTPUT_INVALID"):
        adapter(handler).analyze(*inputs())
    assert len(replies) == 1


def test_timeout_retries_then_succeeds_and_counts_attempts():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ReadTimeout("fixture", request=request)
        return response()

    result = adapter(handler).analyze(*inputs())
    assert len(calls) == 2
    assert result.metadata["attempts"][0]["error_code"] == "MODEL_TIMEOUT"
    assert result.metadata["usage_complete"] is False


def test_timeout_exhausts_finite_retries():
    def handler(request):
        raise httpx.ReadTimeout("secret provider error", request=request)

    with pytest.raises(SemanticFailure) as error:
        adapter(handler, max_retries=2).analyze(*inputs())
    assert str(error.value) == "MODEL_TIMEOUT"
    assert len(error.value.metadata["attempts"]) == 3
    assert "secret provider error" not in json.dumps(error.value.metadata)


@pytest.mark.parametrize("failure", [False, True])
def test_upload_to_api_real_result_and_partial_failure(monkeypatch, failure):
    provider = adapter(lambda request: httpx.Response(401) if failure else response())
    monkeypatch.setattr(main, "analysis_service", MockAnalysisService(main.repository, adapter=provider))
    client = TestClient(main.app)
    asset = client.post("/api/v1/assets", files={"file": ("frame.png", png(), "image/png")}).json()
    job_response = client.post("/api/v1/analysis-jobs", json={
        "target": {"type": "asset", "id": asset["id"]}, "analysis_profile_id": PROFILE.id,
        "requested_outputs": ["features", "aesthetic_analysis", "evidence"]})
    assert job_response.status_code == 202
    job = job_response.json()
    assert job["status"] == ("partial" if failure else "succeeded")
    result = client.get(f"/api/v1/analysis-jobs/{job['id']}/result").json()
    assert result["provenance"]["mode"] == "real"
    assert result["completion_status"] == ("partial" if failure else "complete")
    assert len(result["dimensions"]) == 5
    assert all(f["status"] == "succeeded" for f in result["features"])
    assert result["provenance"]["semantic"]["status"] == ("failed" if failure else "succeeded")
    if failure:
        assert "MODEL_HTTP_401" in result["warnings"]
        assert not any("Mock" in d["interpretation"] for d in result["dimensions"])


@pytest.mark.parametrize("value", ["chat_completions", "typo"])
def test_missing_or_unknown_provider_config_preserves_api_results(monkeypatch, value):
    monkeypatch.setenv("AESTHETICLENS_PROVIDER", value)
    monkeypatch.delenv("AESTHETICLENS_API_KEY", raising=False)
    client = TestClient(main.app)
    asset = client.post("/api/v1/assets", files={"file": ("frame.png", png(), "image/png")}).json()
    created = client.post("/api/v1/analysis-jobs", json={
        "target": {"type": "asset", "id": asset["id"]}, "analysis_profile_id": PROFILE.id,
        "requested_outputs": ["features", "aesthetic_analysis"]})
    assert created.status_code == 202
    assert created.json()["status"] == "partial"
    result = client.get(f"/api/v1/analysis-jobs/{created.json()['id']}/result").json()
    assert "MODEL_CONFIGURATION_INVALID" in result["warnings"]
    assert result["features"]


@pytest.mark.parametrize("status,expected_attempts", [(401, 1), (429, 2), (503, 2)])
def test_http_retry_policy(status, expected_attempts):
    with pytest.raises(SemanticFailure) as error:
        adapter(lambda request: httpx.Response(status)).analyze(*inputs())
    assert len(error.value.metadata["attempts"]) == expected_attempts
