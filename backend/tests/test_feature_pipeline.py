from io import BytesIO

import numpy as np
import pytest
from PIL import Image, ImageCms

from app.config import load_feature_config
from app.feature_pipeline import (
    ExtractorRegistry,
    ImageNormalizationError,
    MetadataExtractor,
    normalize_image,
)
from app.models import (
    AnalysisJob,
    AnalysisTarget,
    Asset,
    JobStatus,
)
from app.repositories import InMemoryRepository
from app.services import MockAnalysisService


def encoded(
    array: np.ndarray,
    *,
    mode="RGB",
    fmt="PNG",
    icc=None,
    exif=None,
) -> bytes:
    output = BytesIO()

    del mode

    image = Image.fromarray(array)
    options = {}

    if icc is not None:
        options["icc_profile"] = icc

    if exif is not None:
        options["exif"] = exif

    image.save(
        output,
        format=fmt,
        **options,
    )

    return output.getvalue()


def values(array: np.ndarray):
    image = normalize_image(
        encoded(array),
        load_feature_config(),
    )

    results = ExtractorRegistry().run(
        image,
        load_feature_config(),
    )

    failed = [
        (
            item.extractor_code,
            item.error_detail,
        )
        for item in results
        if item.status == "failed"
    ]

    assert not failed, failed

    return {
        item.extractor_code: item.values
        for item in results
    }


@pytest.mark.parametrize(
    "level,expected_y,expected_l",
    [
        (0, 0.0, 0.0),
        (128, 0.21586, 53.585),
        (255, 1.0, 100.0),
    ],
)
def test_uniform_reference_values_and_zero_spread(
    level,
    expected_y,
    expected_l,
):
    result = values(
        np.full(
            (32, 32, 3),
            level,
            dtype=np.uint8,
        )
    )

    assert result[
        "relative_luminance"
    ]["mean"] == pytest.approx(
        expected_y,
        abs=5e-4,
    )

    assert result[
        "cie_lightness"
    ]["mean"] == pytest.approx(
        expected_l,
        abs=0.03,
    )

    assert result[
        "global_tonal_contrast"
    ]["lstar_standard_deviation"] < 1e-10

    assert max(
        scale["energy_rms"]
        for scale in result[
            "multiscale_local_contrast"
        ]["scales"]
    ) < 1e-10


def test_split_and_checker_have_equal_distributions_but_different_spatial_signatures():
    split = np.zeros(
        (64, 64, 3),
        dtype=np.uint8,
    )
    split[:, 32:] = 255

    checker = (
        (
            np.indices((64, 64)).sum(axis=0)
            % 2
        )
        * 255
    ).astype(np.uint8)

    checker = np.repeat(
        checker[..., None],
        3,
        axis=2,
    )

    a = values(split)
    b = values(checker)

    assert (
        a["relative_luminance"][
            "histogram"
        ]["counts"]
        ==
        b["relative_luminance"][
            "histogram"
        ]["counts"]
    )

    assert (
        a["global_tonal_contrast"]
        == pytest.approx(
            b["global_tonal_contrast"]
        )
    )

    a_energy = [
        item["energy_rms"]
        for item in a[
            "multiscale_local_contrast"
        ]["scales"]
    ]

    b_energy = [
        item["energy_rms"]
        for item in b[
            "multiscale_local_contrast"
        ]["scales"]
    ]

    assert not np.allclose(
        a_energy,
        b_energy,
        rtol=0.1,
        atol=1e-4,
    )


def test_gradient_has_ordered_distribution():
    gradient = np.tile(
        np.arange(
            256,
            dtype=np.uint8,
        ),
        (32, 1),
    )

    result = values(
        np.repeat(
            gradient[..., None],
            3,
            axis=2,
        )
    )["relative_luminance"]

    assert (
        result["p01"]
        < result["p25"]
        < result["median"]
        < result["p75"]
        < result["p99"]
    )


@pytest.mark.parametrize(
    "fmt",
    [
        "JPEG",
        "PNG",
        "WEBP",
    ],
)
def test_supported_sdr_formats_decode(fmt):
    image = normalize_image(
        encoded(
            np.full(
                (8, 8, 3),
                64,
                dtype=np.uint8,
            ),
            fmt=fmt,
        ),
        load_feature_config(),
    )

    assert image.source_format == fmt


def test_high_bit_depth_encoding_is_rejected_without_tone_mapping():
    data = np.zeros(
        (8, 8),
        dtype=np.uint16,
    )

    with pytest.raises(
        ImageNormalizationError,
        match="UNSUPPORTED_OR_HDR_ENCODING",
    ):
        normalize_image(
            encoded(
                data,
                mode="I;16",
            ),
            load_feature_config(),
        )


def test_icc_tagged_and_assumed_srgb_are_equivalent_and_explicit():
    array = np.full(
        (16, 16, 3),
        90,
        dtype=np.uint8,
    )

    profile = (
        ImageCms.ImageCmsProfile(
            ImageCms.createProfile("sRGB")
        )
        .tobytes()
    )

    tagged = normalize_image(
        encoded(
            array,
            icc=profile,
        ),
        load_feature_config(),
    )

    assumed = normalize_image(
        encoded(array),
        load_feature_config(),
    )

    assert tagged.profile_assumed is False
    assert assumed.profile_assumed is True

    assert tagged.luminance == pytest.approx(
        assumed.luminance,
        abs=1e-8,
    )


def test_invalid_icc_warns_and_falls_back_explicitly():
    image = normalize_image(
        encoded(
            np.zeros(
                (8, 8, 3),
                dtype=np.uint8,
            ),
            icc=b"invalid",
        ),
        load_feature_config(),
    )

    assert image.profile_assumed is True

    assert (
        "ICC_PROFILE_INVALID_ASSUMED_SRGB"
        in image.warnings
    )


def test_exif_orientation_updates_dimensions():
    exif = Image.Exif()
    exif[274] = 6

    image = normalize_image(
        encoded(
            np.zeros(
                (20, 40, 3),
                dtype=np.uint8,
            ),
            fmt="JPEG",
            exif=exif,
        ),
        load_feature_config(),
    )

    metadata = MetadataExtractor().extract(
        image,
        load_feature_config(),
    )

    assert (
        metadata["analysis_width"],
        metadata["analysis_height"],
    ) == (20, 40)


def test_alpha_background_is_explicit_and_reproducible():
    rgba = np.zeros(
        (8, 8, 4),
        dtype=np.uint8,
    )

    first = normalize_image(
        encoded(
            rgba,
            mode="RGBA",
        ),
        load_feature_config(),
    )

    changed = {
        **load_feature_config(),
        "alpha_compositing": {
            **load_feature_config()[
                "alpha_compositing"
            ],
            "display_background_srgb": [
                0.0,
                0.0,
                0.0,
            ],
        },
    }

    second = normalize_image(
        encoded(
            rgba,
            mode="RGBA",
        ),
        changed,
    )

    assert first.luminance.mean() == pytest.approx(
        1.0
    )

    assert second.luminance.mean() == pytest.approx(
        0.0
    )

    assert (
        first.provenance[
            "alpha_compositing"
        ]["space"]
        == "linear-light XYZ D65"
    )


def test_failing_extractor_keeps_successful_results():
    class Failing:
        code = "failing_fixture"
        version = "1"
        schema_version = "1"
        method = "fixture"
        standard = None

        def extract(
            self,
            image,
            config,
        ):
            raise RuntimeError(
                "expected fixture failure"
            )

    image = normalize_image(
        encoded(
            np.zeros(
                (8, 8, 3),
                dtype=np.uint8,
            )
        ),
        load_feature_config(),
    )

    results = ExtractorRegistry(
        [
            MetadataExtractor(),
            Failing(),
        ]
    ).run(
        image,
        load_feature_config(),
    )

    assert [
        item.status
        for item in results
    ] == [
        "succeeded",
        "failed",
    ]

    assert (
        results[0].values[
            "analysis_width"
        ]
        == 8
    )

    assert (
        "expected fixture failure"
        in (
            results[1].error_detail
            or ""
        )
    )

    repository = InMemoryRepository()

    asset = Asset(
        original_filename="fixture.png",
        mime_type="image/png",
        size_bytes=1,
    )

    repository.assets[
        asset.id
    ] = asset

    repository.asset_bytes[
        asset.id
    ] = encoded(
        np.zeros(
            (8, 8, 3),
            dtype=np.uint8,
        )
    )

    job = AnalysisJob(
        target=AnalysisTarget(
            type="asset",
            id=asset.id,
        ),
        analysis_profile_id="aesthetic-core-v1",
        requested_outputs=[
            "features"
        ],
    )

    result = MockAnalysisService(
        repository,
        ExtractorRegistry(
            [
                MetadataExtractor(),
                Failing(),
            ]
        ),
    ).run(job)

    assert job.status == JobStatus.PARTIAL

    assert (
        result.completion_status
        == "partial"
    )

    assert [
        feature.status
        for feature in result.features
    ] == [
        "succeeded",
        "failed",
    ]


def test_cie_chroma_distinguishes_neutral_and_saturated_colour():
    gray = np.full(
        (16, 16, 3),
        128,
        dtype=np.uint8,
    )

    red = np.zeros(
        (16, 16, 3),
        dtype=np.uint8,
    )
    red[..., 0] = 255

    gray_result = values(
        gray
    )["cie_chroma"]

    red_result = values(
        red
    )["cie_chroma"]

    assert gray_result[
        "mean"
    ] == pytest.approx(
        0.0,
        abs=0.05,
    )

    assert red_result[
        "mean"
    ] > 100.0

    assert (
        gray_result["median"]
        <
        red_result["median"]
    )


def test_chromatic_occupancy_separates_gray_and_saturated_color():
    gray = np.full(
        (16, 16, 3),
        128,
        dtype=np.uint8,
    )

    red = np.zeros(
        (16, 16, 3),
        dtype=np.uint8,
    )
    red[..., 0] = 255

    gray_result = values(
        gray
    )["chromatic_occupancy"]

    red_result = values(
        red
    )["chromatic_occupancy"]

    assert gray_result[
        "achromatic_share"
    ] == pytest.approx(1.0)

    assert gray_result[
        "chromatic_share"
    ] == pytest.approx(0.0)

    assert red_result[
        "achromatic_share"
    ] == pytest.approx(0.0)

    assert red_result[
        "chromatic_share"
    ] == pytest.approx(1.0)


def test_hue_distribution_is_undefined_for_gray():
    gray = np.full(
        (16, 16, 3),
        128,
        dtype=np.uint8,
    )

    result = values(
        gray
    )["hue_distribution"]

    assert result["defined"] is False

    assert (
        result[
            "chromatic_pixel_count"
        ]
        == 0
    )

    assert result[
        "effective_hue_count"
    ] == pytest.approx(0.0)


def test_hue_distribution_distinguishes_red_and_blue():
    red = np.zeros(
        (16, 16, 3),
        dtype=np.uint8,
    )
    red[..., 0] = 255

    blue = np.zeros(
        (16, 16, 3),
        dtype=np.uint8,
    )
    blue[..., 2] = 255

    red_result = values(
        red
    )["hue_distribution"]

    blue_result = values(
        blue
    )["hue_distribution"]

    assert red_result[
        "defined"
    ] is True

    assert blue_result[
        "defined"
    ] is True

    assert red_result[
        "circular_resultant_length"
    ] > 0.99

    assert blue_result[
        "circular_resultant_length"
    ] > 0.99

    assert red_result[
        "circular_mean_degrees"
    ] != pytest.approx(
        blue_result[
            "circular_mean_degrees"
        ],
        abs=20.0,
    )


def test_dominant_palette_recovers_red_blue_split():
    image = np.zeros(
        (32, 32, 3),
        dtype=np.uint8,
    )

    image[:, :16, 0] = 255
    image[:, 16:, 2] = 255

    result = values(
        image
    )["dominant_palette"]

    assert len(
        result["colors"]
    ) >= 2

    shares = sorted(
        [
            color["share"]
            for color in result[
                "colors"
            ]
        ],
        reverse=True,
    )

    assert shares[
        0
    ] == pytest.approx(
        0.5,
        abs=0.05,
    )

    assert shares[
        1
    ] == pytest.approx(
        0.5,
        abs=0.05,
    )


def test_warm_cool_proxy_distinguishes_red_and_blue():
    red = np.zeros(
        (16, 16, 3),
        dtype=np.uint8,
    )
    red[..., 0] = 255

    blue = np.zeros(
        (16, 16, 3),
        dtype=np.uint8,
    )
    blue[..., 2] = 255

    red_result = values(
        red
    )["warm_cool_distribution"]

    blue_result = values(
        blue
    )["warm_cool_distribution"]

    assert red_result[
        "warm_share_of_chromatic"
    ] > 0.99

    assert blue_result[
        "cool_share_of_chromatic"
    ] > 0.99


def test_palette_color_contrast_is_zero_for_uniform_and_positive_for_split():
    gray = np.full(
        (16, 16, 3),
        128,
        dtype=np.uint8,
    )

    split = np.zeros(
        (16, 16, 3),
        dtype=np.uint8,
    )

    split[:, :8, 0] = 255
    split[:, 8:, 2] = 255

    gray_result = values(
        gray
    )["palette_color_contrast"]

    split_result = values(
        split
    )["palette_color_contrast"]

    assert gray_result[
        "max_delta_e2000"
    ] == pytest.approx(0.0)

    assert split_result[
        "max_delta_e2000"
    ] > 0.0


def test_colorfulness_is_higher_for_saturated_colour_than_gray():
    gray = np.full(
        (16, 16, 3),
        128,
        dtype=np.uint8,
    )

    red = np.zeros(
        (16, 16, 3),
        dtype=np.uint8,
    )
    red[..., 0] = 255

    gray_result = values(
        gray
    )["image_colorfulness"]

    red_result = values(
        red
    )["image_colorfulness"]

    assert gray_result[
        "colorfulness"
    ] == pytest.approx(
        0.0,
        abs=0.01,
    )

    assert (
        red_result[
            "colorfulness"
        ]
        >
        gray_result[
            "colorfulness"
        ]
    )

def test_tonal_occupancy_distinguishes_black_gray_and_white():
    black = np.zeros((16, 16, 3), dtype=np.uint8)
    gray = np.full((16, 16, 3), 128, dtype=np.uint8)
    white = np.full((16, 16, 3), 255, dtype=np.uint8)

    black_result = values(black)["tonal_occupancy"]
    gray_result = values(gray)["tonal_occupancy"]
    white_result = values(white)["tonal_occupancy"]

    assert black_result["shadow_share"] == pytest.approx(1.0)
    assert black_result["highlight_share"] == pytest.approx(0.0)
    assert black_result["occupancy_sum"] == pytest.approx(1.0)

    assert gray_result["midtone_share"] == pytest.approx(1.0)
    assert gray_result["occupancy_sum"] == pytest.approx(1.0)

    assert white_result["shadow_share"] == pytest.approx(0.0)
    assert white_result["highlight_share"] == pytest.approx(1.0)
    assert white_result["occupancy_sum"] == pytest.approx(1.0)
    assert white_result["configuration_version"] == "1.0.0"
