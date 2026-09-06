from io import BytesIO

import numpy as np
import pytest
from PIL import Image, ImageCms

from app.config import load_feature_config
from app.feature_pipeline import ExtractorRegistry, ImageNormalizationError, MetadataExtractor, normalize_image
from app.models import AnalysisJob, AnalysisTarget, Asset, JobStatus
from app.repositories import InMemoryRepository
from app.services import MockAnalysisService


def encoded(array: np.ndarray, *, mode="RGB", fmt="PNG", icc=None, exif=None) -> bytes:
    output = BytesIO()
    del mode  # Array shape/dtype determines the fixture mode in current Pillow.
    image = Image.fromarray(array)
    options = {}
    if icc is not None: options["icc_profile"] = icc
    if exif is not None: options["exif"] = exif
    image.save(output, format=fmt, **options)
    return output.getvalue()


def values(array: np.ndarray):
    image = normalize_image(encoded(array), load_feature_config())
    return {item.extractor_code: item.values for item in ExtractorRegistry().run(image, load_feature_config())}


@pytest.mark.parametrize("level,expected_y,expected_l", [(0, 0.0, 0.0), (128, 0.21586, 53.585), (255, 1.0, 100.0)])
def test_uniform_reference_values_and_zero_spread(level, expected_y, expected_l):
    result = values(np.full((32, 32, 3), level, dtype=np.uint8))
    assert result["relative_luminance"]["mean"] == pytest.approx(expected_y, abs=5e-4)
    assert result["cie_lightness"]["mean"] == pytest.approx(expected_l, abs=0.03)
    assert result["global_tonal_contrast"]["lstar_standard_deviation"] < 1e-10
    assert max(scale["energy_rms"] for scale in result["multiscale_local_contrast"]["scales"]) < 1e-10


def test_split_and_checker_have_equal_distributions_but_different_spatial_signatures():
    split = np.zeros((64, 64, 3), dtype=np.uint8); split[:, 32:] = 255
    checker = ((np.indices((64, 64)).sum(axis=0) % 2) * 255).astype(np.uint8)
    checker = np.repeat(checker[..., None], 3, axis=2)
    a, b = values(split), values(checker)
    assert a["relative_luminance"]["histogram"]["counts"] == b["relative_luminance"]["histogram"]["counts"]
    assert a["global_tonal_contrast"] == pytest.approx(b["global_tonal_contrast"])
    a_energy = [x["energy_rms"] for x in a["multiscale_local_contrast"]["scales"]]
    b_energy = [x["energy_rms"] for x in b["multiscale_local_contrast"]["scales"]]
    assert not np.allclose(a_energy, b_energy, rtol=0.1, atol=1e-4)


def test_gradient_has_ordered_distribution():
    gradient = np.tile(np.arange(256, dtype=np.uint8), (32, 1))
    result = values(np.repeat(gradient[..., None], 3, axis=2))["relative_luminance"]
    assert result["p01"] < result["p25"] < result["median"] < result["p75"] < result["p99"]


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP"])
def test_supported_sdr_formats_decode(fmt):
    image = normalize_image(encoded(np.full((8, 8, 3), 64, dtype=np.uint8), fmt=fmt), load_feature_config())
    assert image.source_format == fmt


def test_high_bit_depth_encoding_is_rejected_without_tone_mapping():
    data = np.zeros((8, 8), dtype=np.uint16)
    with pytest.raises(ImageNormalizationError, match="UNSUPPORTED_OR_HDR_ENCODING"):
        normalize_image(encoded(data, mode="I;16"), load_feature_config())


def test_icc_tagged_and_assumed_srgb_are_equivalent_and_explicit():
    array = np.full((16, 16, 3), 90, dtype=np.uint8)
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    tagged = normalize_image(encoded(array, icc=profile), load_feature_config())
    assumed = normalize_image(encoded(array), load_feature_config())
    assert tagged.profile_assumed is False
    assert assumed.profile_assumed is True
    assert tagged.luminance == pytest.approx(assumed.luminance, abs=1e-8)


def test_invalid_icc_warns_and_falls_back_explicitly():
    image = normalize_image(encoded(np.zeros((8, 8, 3), dtype=np.uint8), icc=b"invalid"), load_feature_config())
    assert image.profile_assumed is True
    assert "ICC_PROFILE_INVALID_ASSUMED_SRGB" in image.warnings


def test_exif_orientation_updates_dimensions():
    exif = Image.Exif(); exif[274] = 6
    image = normalize_image(encoded(np.zeros((20, 40, 3), dtype=np.uint8), fmt="JPEG", exif=exif), load_feature_config())
    metadata = MetadataExtractor().extract(image, load_feature_config())
    assert (metadata["analysis_width"], metadata["analysis_height"]) == (20, 40)


def test_alpha_background_is_explicit_and_reproducible():
    rgba = np.zeros((8, 8, 4), dtype=np.uint8)
    first = normalize_image(encoded(rgba, mode="RGBA"), load_feature_config())
    changed = {**load_feature_config(), "alpha_compositing": {**load_feature_config()["alpha_compositing"], "display_background_srgb": [0.0, 0.0, 0.0]}}
    second = normalize_image(encoded(rgba, mode="RGBA"), changed)
    assert first.luminance.mean() == pytest.approx(1.0)
    assert second.luminance.mean() == pytest.approx(0.0)
    assert first.provenance["alpha_compositing"]["space"] == "linear-light XYZ D65"


def test_failing_extractor_keeps_successful_results():
    class Failing:
        code, version, schema_version, method, standard = "failing_fixture", "1", "1", "fixture", None
        def extract(self, image, config): raise RuntimeError("expected fixture failure")
    image = normalize_image(encoded(np.zeros((8, 8, 3), dtype=np.uint8)), load_feature_config())
    results = ExtractorRegistry([MetadataExtractor(), Failing()]).run(image, load_feature_config())
    assert [item.status for item in results] == ["succeeded", "failed"]
    assert results[0].values["analysis_width"] == 8
    assert "expected fixture failure" in (results[1].error_detail or "")

    repository = InMemoryRepository()
    asset = Asset(original_filename="fixture.png", mime_type="image/png", size_bytes=1)
    repository.assets[asset.id] = asset
    repository.asset_bytes[asset.id] = encoded(np.zeros((8, 8, 3), dtype=np.uint8))
    job = AnalysisJob(target=AnalysisTarget(type="asset", id=asset.id), analysis_profile_id="aesthetic-core-v1", requested_outputs=["features"])
    result = MockAnalysisService(repository, ExtractorRegistry([MetadataExtractor(), Failing()])).run(job)
    assert job.status == JobStatus.PARTIAL
    assert result.completion_status == "partial"
    assert [feature.status for feature in result.features] == ["succeeded", "failed"]
