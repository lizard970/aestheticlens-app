from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app


client = TestClient(app)


def test_capabilities_expose_available_and_future_modules():
    response = client.get("/api/v1/capabilities")

    assert response.status_code == 200

    codes = {
        item["code"]: item["status"]
        for item in response.json()["capabilities"]
    }

    assert codes["single_image_analysis"] == "available"
    assert codes["hybrid_retrieval"] == "not_implemented"


def png_bytes() -> bytes:
    output = BytesIO()

    Image.new(
        "RGB",
        (8, 8),
        (128, 128, 128),
    ).save(
        output,
        format="PNG",
    )

    return output.getvalue()


def test_hybrid_analysis_keeps_mock_contract_and_adds_real_features():
    upload = client.post(
        "/api/v1/assets",
        files={
            "file": (
                "frame.png",
                png_bytes(),
                "image/png",
            )
        },
    )

    assert upload.status_code == 201

    asset_id = upload.json()["id"]

    created = client.post(
        "/api/v1/analysis-jobs",
        json={
            "target": {
                "type": "asset",
                "id": asset_id,
            },
            "analysis_profile_id": "aesthetic-core-v1",
            "requested_outputs": [
                "features",
                "aesthetic_analysis",
                "evidence",
            ],
        },
    )

    assert created.status_code == 202

    job_id = created.json()["id"]

    result = client.get(
        f"/api/v1/analysis-jobs/{job_id}/result"
    )

    assert result.status_code == 200

    payload = result.json()

    assert payload["provenance"]["mode"] == "hybrid"
    assert len(payload["dimensions"]) == 5
    assert payload["completion_status"] == "complete"

    extractor_codes = {
        feature["extractor_code"]
        for feature in payload["features"]
    }

    required_extractors = {
        "image_metadata",
        "relative_luminance",
        "cie_lightness",
        "cie_chroma",
        "chromatic_occupancy",
        "hue_distribution",
        "dominant_palette",
        "warm_cool_distribution",
        "palette_color_contrast",
        "image_colorfulness",
        "global_tonal_contrast",
        "multiscale_local_contrast",
        "source_endpoint_occupancy",
    }

    assert required_extractors.issubset(
        extractor_codes
    )


def test_corrupted_image_is_a_stable_failed_job_error():
    upload = client.post(
        "/api/v1/assets",
        files={
            "file": (
                "broken.png",
                b"not-an-image",
                "image/png",
            )
        },
    )

    assert upload.status_code == 201

    created = client.post(
        "/api/v1/analysis-jobs",
        json={
            "target": {
                "type": "asset",
                "id": upload.json()["id"],
            },
            "analysis_profile_id": "aesthetic-core-v1",
            "requested_outputs": ["features"],
        },
    )

    assert created.status_code == 422
    assert (
        created.json()["detail"]
        == "IMAGE_DECODE_FAILED"
    )