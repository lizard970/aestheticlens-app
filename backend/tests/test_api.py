from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_capabilities_expose_available_and_future_modules():
    response = client.get("/api/v1/capabilities")
    assert response.status_code == 200
    codes = {item["code"]: item["status"] for item in response.json()["capabilities"]}
    assert codes["single_image_analysis"] == "available"
    assert codes["hybrid_retrieval"] == "not_implemented"


def test_mock_analysis_contract():
    upload = client.post("/api/v1/assets", files={"file": ("frame.png", b"fake-png", "image/png")})
    assert upload.status_code == 201
    asset_id = upload.json()["id"]

    created = client.post("/api/v1/analysis-jobs", json={
        "target": {"type": "asset", "id": asset_id},
        "analysis_profile_id": "aesthetic-core-v1",
        "requested_outputs": ["features", "aesthetic_analysis", "evidence"],
    })
    assert created.status_code == 202
    job_id = created.json()["id"]

    result = client.get(f"/api/v1/analysis-jobs/{job_id}/result")
    assert result.status_code == 200
    assert result.json()["provenance"]["mode"] == "mock"
    assert len(result.json()["dimensions"]) == 5
