from copy import deepcopy
from io import BytesIO
import json

import numpy as np
import pytest
from PIL import Image
from scipy.ndimage import gaussian_filter

from app.config import load_feature_config
from app.feature_pipeline import (AccentPaletteExtractor, DominantPaletteExtractor,
                                  _composition_saliency, _spatial_maps, normalize_image)


def extract(pixels, config=None):
    config = config or deepcopy(load_feature_config())
    output = BytesIO()
    Image.fromarray(pixels).save(output, format="PNG")
    image = normalize_image(output.getvalue(), config)
    return (DominantPaletteExtractor().extract(image, config),
            AccentPaletteExtractor().extract(image, config), image)


@pytest.mark.parametrize("width", [4, 1])
def test_dark_majority_retains_small_cyan_and_real_full_image_coverage(width):
    pixels = np.zeros((100, 100, 3), dtype=np.uint8)
    pixels[:, 80:] = [40, 40, 40]
    pixels[:, 80:80 + width] = [0, 180, 220]
    dominant, accent, _ = extract(pixels)
    assert dominant["colors"][0]["share"] == pytest.approx(.8)
    assert accent["defined"] is True
    color = next(c for c in accent["colors"] if c["hex_srgb"] == "#00B4DC")
    assert color["share"] == pytest.approx(width / 100)
    assert color["coverage_percentage"] == pytest.approx(width)
    assert color["chroma"] >= 20
    assert color["contrast_delta_e2000"] >= 10
    assert accent["saliency_available"] is True
    assert color["saliency_lift"] > 1
    if width == 1:
        assert not any(c["hex_srgb"] == "#00B4DC" for c in dominant["colors"])


@pytest.mark.parametrize("rgb", [[0, 0, 0], [128, 128, 128], [255, 0, 0], [0, 180, 220]])
def test_monochrome_has_one_dominant_and_no_accents(rgb):
    dominant, accent, _ = extract(np.full((24, 24, 3), rgb, dtype=np.uint8))
    assert len(dominant["colors"]) == 1
    assert dominant["coverage"] == pytest.approx(1)
    assert accent["colors"] == []
    assert accent["defined"] is False


def test_grayscale_gradient_has_no_chromatic_accents():
    pixels = np.repeat(np.tile(np.arange(256, dtype=np.uint8), (16, 1))[..., None], 3, axis=2)
    dominant, accent, _ = extract(pixels)
    assert len(dominant["colors"]) > 1
    assert accent["colors"] == []


def test_multicolor_ranking_determinism_and_dominant_compatibility():
    pixels = np.zeros((100, 100, 3), dtype=np.uint8)
    pixels[:, 70:80] = [255, 0, 0]
    pixels[:, 80:85] = [0, 180, 220]
    pixels[:, 85:90] = [0, 255, 0]
    pixels[:, 90:] = [60, 60, 60]
    config = deepcopy(load_feature_config())
    dominant, accent, image = extract(pixels, config)
    assert len(accent["colors"]) == 3
    assert {c["hex_srgb"] for c in accent["colors"]} == {"#FF0000", "#00B4DC", "#00FF00"}
    assert [c["share"] for c in dominant["colors"]] == sorted([c["share"] for c in dominant["colors"]], reverse=True)
    assert [c["accent_score"] for c in accent["colors"]] == sorted([c["accent_score"] for c in accent["colors"]], reverse=True)
    assert AccentPaletteExtractor().extract(image, config) == accent
    del config["color_analysis"]["accent_palette"]
    assert DominantPaletteExtractor().extract(image, config) == dominant
    json.dumps(accent, allow_nan=False)


def test_low_chroma_and_isolated_noise_are_not_promoted():
    pixels = np.full((100, 100, 3), 100, dtype=np.uint8)
    pixels[:, :4] = [110, 100, 100]
    pixels[0, 0] = [255, 0, 0]
    assert extract(pixels)[1]["colors"] == []


def test_high_chroma_alone_does_not_make_a_nearby_color_an_accent():
    pixels = np.full((100, 100, 3), [255, 0, 0], dtype=np.uint8)
    pixels[:, :4] = [250, 10, 10]
    assert extract(pixels)[1]["colors"] == []


def test_chromatic_candidate_sampling_is_independent_of_background_sampling():
    pixels = np.zeros((100, 100, 3), dtype=np.uint8)
    pixels[30:40, 30:40] = [0, 180, 220]
    config = deepcopy(load_feature_config())
    config["color_analysis"]["palette"]["sample_limit"] = 2
    dominant, accent, _ = extract(pixels, config)
    assert [c["hex_srgb"] for c in dominant["colors"]] == ["#000000"]
    assert accent["colors"][0]["hex_srgb"] == "#00B4DC"
    assert accent["colors"][0]["share"] == pytest.approx(.01)


def test_saliency_reuse_preserves_previous_formula_and_has_neutral_fallback():
    pixels = np.zeros((100, 100, 3), dtype=np.uint8)
    pixels[:, :4] = [0, 180, 220]
    config = deepcopy(load_feature_config())
    _, accent, image = extract(pixels, config)
    maps = _spatial_maps(image, config)
    settings = config["composition_analysis"]
    expected = gaussian_filter(maps["gradient"] * settings["saliency_gradient_weight"] + maps["local_std"] * settings["saliency_texture_weight"],
        sigma=max(config["space_analysis"]["minimum_sigma_pixels"], settings["saliency_smoothing_fraction"] * 100), mode=config["space_analysis"]["boundary_mode"])
    np.testing.assert_array_equal(_composition_saliency(image, config), expected)
    config["composition_analysis"]["saliency_signal_floor"] = 100
    fallback = AccentPaletteExtractor().extract(image, config)
    assert fallback["saliency_available"] is False
    assert fallback["colors"][0]["saliency_lift"] is None
    assert fallback["colors"][0]["share"] == accent["colors"][0]["share"]
    assert fallback["colors"][0]["accent_score"] < accent["colors"][0]["accent_score"]
