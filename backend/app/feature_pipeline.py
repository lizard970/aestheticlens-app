from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any, Protocol

import numpy as np
import PIL
import scipy
import skimage
from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError
from scipy.cluster.vq import kmeans2, vq
from scipy.ndimage import gaussian_filter
from skimage.color import (
    deltaE_ciede2000,
    lab2rgb,
    rgb2lab,
    rgb2xyz,
    xyz2rgb,
)

from .models import FeatureResult


class ImageNormalizationError(ValueError):
    pass


@dataclass
class NormalizedImage:
    source_width: int
    source_height: int
    width: int
    height: int
    source_format: str
    source_mode: str
    profile_source: str
    profile_assumed: bool
    alpha_present: bool
    luminance: np.ndarray
    lightness: np.ndarray
    srgb: np.ndarray
    lab: np.ndarray
    source_black_occupancy: float | None
    source_white_occupancy: float | None
    warnings: list[str]
    provenance: dict[str, Any]


def _source_endpoint_occupancy(image: Image.Image) -> tuple[float | None, float | None]:
    if image.mode not in {"L", "LA", "RGB", "RGBA"}:
        return None, None
    values = np.asarray(image)
    channels = values[..., :1] if image.mode in {"L", "LA"} else values[..., :3]
    return float(np.all(channels == 0, axis=-1).mean()), float(np.all(channels == 255, axis=-1).mean())


def normalize_image(body: bytes, config: dict[str, Any]) -> NormalizedImage:
    warnings: list[str] = []
    try:
        source = Image.open(BytesIO(body))
        source.load()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageNormalizationError("IMAGE_DECODE_FAILED") from exc
    source_size = source.size
    source_format, source_mode = source.format or "unknown", source.mode
    if source_mode in {"I", "F", "I;16", "I;16B", "I;16L"}:
        raise ImageNormalizationError(f"UNSUPPORTED_OR_HDR_ENCODING:{source_mode}")
    oriented = ImageOps.exif_transpose(source)
    black, white = _source_endpoint_occupancy(oriented)
    alpha_present = "A" in oriented.getbands()
    alpha_image = oriented.getchannel("A") if alpha_present else None
    icc = oriented.info.get("icc_profile")
    profile_assumed = not bool(icc)
    profile_source = "embedded ICC"
    if not icc:
        profile_source = "assumed sRGB IEC61966-2-1"
        warnings.append("ICC_PROFILE_MISSING_ASSUMED_SRGB")
    try:
        rgb_source = oriented.convert("RGB") if alpha_present else oriented
        if icc:
            rgb = ImageCms.profileToProfile(rgb_source, ImageCms.ImageCmsProfile(BytesIO(icc)), ImageCms.createProfile("sRGB"), outputMode="RGB")
        elif rgb_source.mode in {"RGB", "L"}:
            rgb = rgb_source.convert("RGB")
        else:
            raise ImageNormalizationError(f"UNSUPPORTED_UNPROFILED_MODE:{rgb_source.mode}")
    except ImageNormalizationError:
        raise
    except (ImageCms.PyCMSError, OSError, ValueError) as exc:
        warnings.append("ICC_PROFILE_INVALID_ASSUMED_SRGB")
        profile_source, profile_assumed = "invalid embedded ICC; assumed sRGB IEC61966-2-1", True
        if oriented.mode not in {"RGB", "RGBA", "L", "LA"}:
            raise ImageNormalizationError("INVALID_ICC_FOR_NON_SRGB_MODE") from exc
        rgb = oriented.convert("RGB")

    max_dimension = int(config["analysis_raster"]["max_dimension"])
    if max(rgb.size) > max_dimension:
        ratio = max_dimension / max(rgb.size)
        resized = (max(1, round(rgb.width * ratio)), max(1, round(rgb.height * ratio)))
        rgb = rgb.resize(resized, Image.Resampling.LANCZOS)
        alpha_image = alpha_image.resize(resized, Image.Resampling.LANCZOS) if alpha_image else None
        warnings.append("ANALYSIS_RASTER_RESIZED")

    srgb = np.asarray(rgb, dtype=np.float64) / 255.0
    xyz = rgb2xyz(srgb)
    if alpha_image is not None:
        alpha = np.asarray(alpha_image, dtype=np.float64) / 255.0
        background = np.asarray(config["alpha_compositing"]["display_background_srgb"], dtype=np.float64).reshape(1, 1, 3)
        xyz = xyz * alpha[..., None] + rgb2xyz(background)[0, 0] * (1.0 - alpha[..., None])
        srgb = xyz2rgb(xyz)
    lab = rgb2lab(srgb, illuminant="D65", observer="2")
    provenance = {
        "source_format": source_format, "source_mode": source_mode,
        "source_dimensions": list(source_size), "orientation_corrected_dimensions": list(oriented.size),
        "analysis_raster_dimensions": [rgb.width, rgb.height], "profile_source": profile_source,
        "profile_assumed": profile_assumed, "working_representation": config["working_representation"],
        "reference_white": config["reference_white"], "alpha_present": alpha_present,
        "alpha_compositing": config["alpha_compositing"] if alpha_present else None,
        "libraries": {"Pillow": PIL.__version__, "numpy": np.__version__, "scikit-image": skimage.__version__, "scipy": scipy.__version__, "colour_engine": "LittleCMS via Pillow ImageCms"},
    }
    return NormalizedImage(
    source_width=source_size[0],
    source_height=source_size[1],
    width=rgb.width,
    height=rgb.height,
    source_format=source_format,
    source_mode=source_mode,
    profile_source=profile_source,
    profile_assumed=profile_assumed,
    alpha_present=alpha_present,
    srgb=srgb,
    lab=lab,
    luminance=xyz[..., 1],
    lightness=lab[..., 0],
    source_black_occupancy=black,
    source_white_occupancy=white,
    warnings=warnings,
    provenance=provenance,
)


class VisualFeatureExtractor(Protocol):
    code: str
    version: str
    schema_version: str
    method: str
    standard: str | None
    def extract(self, image: NormalizedImage, config: dict[str, Any]) -> dict[str, Any]: ...


class BaseExtractor:
    version, schema_version, standard = "1.0.0", "1.0.0", None


class MetadataExtractor(BaseExtractor):
    code, method = "image_metadata", "Decoded metadata and normalization provenance"
    def extract(self, image, config):
        return {"source_width": image.source_width, "source_height": image.source_height, "analysis_width": image.width, "analysis_height": image.height, "format": image.source_format, "mode": image.source_mode, "profile_assumed": image.profile_assumed, "alpha_present": image.alpha_present}


def _distribution(values: np.ndarray, value_range: tuple[float, float], bins: int) -> dict[str, Any]:
    p = np.percentile(values, [1, 5, 25, 50, 75, 95, 99])
    counts, edges = np.histogram(values, bins=bins, range=value_range)
    return {"mean": float(values.mean()), "median": float(p[3]), "p01": float(p[0]), "p05": float(p[1]), "p25": float(p[2]), "p75": float(p[4]), "p95": float(p[5]), "p99": float(p[6]), "histogram": {"counts": counts.tolist(), "bin_edges": edges.tolist(), "range": list(value_range)}}


class LuminanceExtractor(BaseExtractor):
    code, method, standard = "relative_luminance", "Distribution of linear-light relative luminance Y", "IEC 61966-2-1 to CIE XYZ D65"
    def extract(self, image, config): return _distribution(image.luminance, (0.0, 1.0), int(config["histogram_bins"]))


class LightnessExtractor(BaseExtractor):
    code, method, standard = "cie_lightness", "Distribution of CIELAB L*", "CIE 1976 L*a*b*, D65 2-degree"
    def extract(self, image, config): return _distribution(image.lightness, (0.0, 100.0), int(config["histogram_bins"]))


def _lab_chroma(lab: np.ndarray) -> np.ndarray:
    a = lab[..., 1]
    b = lab[..., 2]
    hue = np.degrees(np.arctan2(b, a))
    return np.hypot(a, b)

def _lab_hue_degrees(lab: np.ndarray) -> np.ndarray:
    a = lab[..., 1]
    b = lab[..., 2]

    hue = np.degrees(np.arctan2(b, a))
    return np.mod(hue, 360.0)


def _lab_to_lch(lab: np.ndarray) -> np.ndarray:
    chroma = _lab_chroma(lab)
    hue = _lab_hue_degrees(lab)

    return np.stack(
        [lab[..., 0], chroma, hue],
        axis=-1,
    )


def _rgb_to_hex(rgb: np.ndarray) -> str:
    values = np.clip(
        np.rint(rgb * 255.0),
        0,
        255,
    ).astype(np.uint8)

    return "#{:02X}{:02X}{:02X}".format(*values.tolist())


def _angle_in_ranges(
    angles: np.ndarray,
    ranges: list[list[float]],
) -> np.ndarray:
    mask = np.zeros(angles.shape, dtype=bool)

    for start, end in ranges:
        start = float(start)
        end = float(end)

        if start <= end:
            mask |= (angles >= start) & (angles < end)
        else:
            mask |= (angles >= start) | (angles < end)

    return mask


def _dominant_palette(
    image: NormalizedImage,
    config: dict[str, Any],
) -> dict[str, Any]:
    settings = config["color_analysis"]["palette"]

    cluster_count = int(settings["cluster_count"])
    sample_limit = int(settings["sample_limit"])
    min_share = float(settings["min_cluster_share"])
    random_seed = int(settings["random_seed"])
    max_iterations = int(settings["max_iterations"])

    flat_lab = image.lab.reshape(-1, 3)

    if len(flat_lab) > sample_limit:
        indices = np.linspace(
            0,
            len(flat_lab) - 1,
            sample_limit,
            dtype=np.int64,
        )
        sample = flat_lab[indices]
    else:
        sample = flat_lab

    unique_sample = np.unique(sample, axis=0)
    actual_k = min(cluster_count, len(unique_sample))

    if actual_k == 0:
        return {
            "colors": [],
            "requested_cluster_count": cluster_count,
            "actual_cluster_count": 0,
            "coverage": 0.0,
        }

    if actual_k == 1:
        centers = unique_sample[:1]
    else:
        centers, _ = kmeans2(
            sample,
            actual_k,
            iter=max_iterations,
            minit="++",
            rng=np.random.default_rng(random_seed),
        )

    labels, _ = vq(flat_lab, centers)
    counts = np.bincount(labels, minlength=len(centers))
    shares = counts / counts.sum()

    order = np.argsort(shares)[::-1]

    colors: list[dict[str, Any]] = []

    for index in order:
        share = float(shares[index])

        if share < min_share:
            continue

        lab_color = centers[index]
        lch_color = _lab_to_lch(
            lab_color.reshape(1, 1, 3)
        )[0, 0]

        rgb_color = lab2rgb(
            lab_color.reshape(1, 1, 3),
            illuminant="D65",
            observer="2",
        )[0, 0]

        colors.append({
            "rank": len(colors) + 1,
            "share": share,
            "hex_srgb": _rgb_to_hex(rgb_color),
            "lab": [float(x) for x in lab_color],
            "lch": [float(x) for x in lch_color],
        })

    return {
        "colors": colors,
        "requested_cluster_count": cluster_count,
        "actual_cluster_count": len(centers),
        "coverage": float(sum(color["share"] for color in colors)),
    }


class ChromaExtractor(BaseExtractor):
    code = "cie_chroma"
    method = "Distribution of CIELAB chroma C*ab"
    standard = "CIE 1976 L*a*b* cylindrical chroma C*ab"

    def extract(self, image, config):
        chroma = _lab_chroma(image.lab)

        settings = config["color_analysis"]
        value_range = tuple(settings["chroma_histogram_range"])

        result = _distribution(
            chroma,
            value_range,
            int(settings["chroma_histogram_bins"]),
        )

        result["iqr"] = result["p75"] - result["p25"]

        return result

class ChromaticOccupancyExtractor(BaseExtractor):
    code = "chromatic_occupancy"
    method = "Pixel occupancy above and below configurable CIELAB chroma threshold"
    standard = "CIELAB C*ab with configurable achromatic threshold"

    def extract(self, image, config):
        chroma = _lab_chroma(image.lab)
        floor = float(
            config["color_analysis"]["achromatic_chroma_floor"]
        )

        achromatic = chroma < floor

        return {
            "chroma_floor": floor,
            "achromatic_share": float(achromatic.mean()),
            "chromatic_share": float((~achromatic).mean()),
        }

class HueDistributionExtractor(BaseExtractor):
    code = "hue_distribution"
    method = "Chroma-weighted CIELAB hue-angle distribution over chromatic pixels"
    standard = "CIE 1976 L*a*b* hue angle h*ab"

    def extract(self, image, config):
        settings = config["color_analysis"]

        chroma = _lab_chroma(image.lab)
        hue = _lab_hue_degrees(image.lab)

        floor = float(settings["achromatic_chroma_floor"])
        bins = int(settings["hue_histogram_bins"])

        mask = chroma >= floor

        if not np.any(mask):
            return {
                "defined": False,
                "chromatic_pixel_count": 0,
                "bin_edges_degrees": np.linspace(
                    0.0, 360.0, bins + 1
                ).tolist(),
                "weighted_histogram": [0.0] * bins,
                "circular_mean_degrees": None,
                "circular_resultant_length": 0.0,
                "effective_hue_count": 0.0,
            }

        selected_hue = hue[mask]
        weights = chroma[mask]

        counts, edges = np.histogram(
            selected_hue,
            bins=bins,
            range=(0.0, 360.0),
            weights=weights,
        )

        normalized = counts / counts.sum()

        radians = np.radians(selected_hue)

        x = np.sum(weights * np.cos(radians))
        y = np.sum(weights * np.sin(radians))

        mean_angle = np.degrees(np.arctan2(y, x)) % 360.0

        resultant = (
            np.sqrt(x ** 2 + y ** 2)
            / np.sum(weights)
        )

        positive = normalized[normalized > 0]
        entropy = -np.sum(positive * np.log(positive))
        effective_hue_count = np.exp(entropy)

        return {
            "defined": True,
            "chromatic_pixel_count": int(mask.sum()),
            "bin_edges_degrees": edges.tolist(),
            "weighted_histogram": normalized.tolist(),
            "circular_mean_degrees": float(mean_angle),
            "circular_resultant_length": float(resultant),
            "effective_hue_count": float(effective_hue_count),
        }

class DominantPaletteExtractor(BaseExtractor):
    code = "dominant_palette"
    method = "Deterministic k-means dominant-colour quantization in CIELAB"
    standard = "CIELAB D65 perceptual colour space"

    def extract(self, image, config):
        return _dominant_palette(image, config)


class AccentPaletteExtractor(BaseExtractor):
    code = "accent_palette"
    method = "Chroma-conditioned CIELAB k-means candidates ranked by coverage, chroma, CIEDE2000 and spatial saliency"
    standard = "CIELAB D65, CIEDE2000; configurable emphasis heuristic, not an aesthetic score"

    def extract(self, image, config):
        settings = config["color_analysis"]["accent_palette"]
        output = {
            "configuration_version": settings["version"],
            "colors": [], "coverage": 0.0, "defined": False,
            "saliency_available": False,
            "interpretation_limit": "Chromatic emphasis candidates on the normalized raster; not semantic attention or calibrated probabilities",
        }
        flat_lab = image.lab.reshape(-1, 3)
        # Sample the chromatic population separately so low-chroma backgrounds cannot
        # consume every cluster. Coverage is still measured against ALL raster pixels.
        chromatic = _lab_chroma(flat_lab) >= float(settings["min_chroma"])
        candidates = flat_lab[chromatic]
        if not len(candidates):
            return output
        limit = int(settings["sample_limit"])
        sample = candidates[np.linspace(0, len(candidates) - 1, min(limit, len(candidates)), dtype=np.int64)]
        unique = np.unique(sample, axis=0)
        k = min(int(settings["cluster_count"]), len(unique))
        centers = unique[:1] if k == 1 else kmeans2(
            sample, k, iter=int(settings["max_iterations"]), minit="++",
            rng=np.random.default_rng(int(settings["random_seed"])),
        )[0]
        labels, _ = vq(candidates, centers)
        counts = np.bincount(labels, minlength=len(centers))
        shares = counts / len(flat_lab)

        dominant = _dominant_palette(image, config)["colors"]
        if not dominant:
            return output
        # Compare against large-area context, not the accent's own dominant-palette
        # entry. A 4% colour may legitimately occur in both output palettes.
        background = [c["lab"] for c in dominant if c["share"] > float(settings["max_coverage"])]
        reference = np.asarray(background or [dominant[0]["lab"]])

        lifts = np.ones(len(centers))
        if "composition_analysis" in config and "space_analysis" in config:
            saliency = _composition_saliency(image, config)
            mean = float(saliency.mean())
            composition = config["composition_analysis"]
            reliable = mean >= float(composition["saliency_signal_floor"]) and mean > 0 and float(saliency.max()) / mean >= float(composition["saliency_peak_to_mean_min"])
            output["saliency_available"] = bool(reliable)
            if reliable:
                totals = np.bincount(labels, weights=saliency.ravel()[chromatic], minlength=len(centers))
                lifts = totals / np.maximum(counts, 1) / mean

        ranked = []
        for index, center in enumerate(centers):
            share = float(shares[index])
            chroma = float(_lab_chroma(center))
            distance = float(np.min(deltaE_ciede2000(center[None, :], reference)))
            if not (float(settings["min_coverage"]) <= share <= float(settings["max_coverage"])) or chroma < float(settings["min_chroma"]) or distance < float(settings["min_delta_e2000"]):
                continue
            support = np.sqrt(min(share / float(settings["coverage_support_reference"]), 1.0))
            chroma_strength = chroma / (chroma + float(settings["min_chroma"]))
            contrast_strength = distance / (distance + float(settings["min_delta_e2000"]))
            lift = float(lifts[index])
            saliency_bonus = max(0.0, (lift - 1.0) / (lift + 1.0))
            score = support * chroma_strength * contrast_strength * (1.0 + float(settings["saliency_weight"]) * saliency_bonus)
            ranked.append({
                "share": share, "coverage_percentage": share * 100.0,
                "hex_srgb": _rgb_to_hex(lab2rgb(center.reshape(1, 1, 3), illuminant="D65", observer="2")[0, 0]),
                "lab": center.tolist(), "lch": _lab_to_lch(center).tolist(),
                "chroma": chroma, "contrast_delta_e2000": distance,
                "saliency_lift": lift if output["saliency_available"] else None,
                "accent_score": float(score),
            })
        ranked.sort(key=lambda c: (-c["accent_score"], -c["share"], c["hex_srgb"]))
        for color in ranked:
            if any(float(deltaE_ciede2000(np.asarray(color["lab"]), np.asarray(prior["lab"]))) < float(settings["deduplicate_delta_e2000"]) for prior in output["colors"]):
                continue
            output["colors"].append({"rank": len(output["colors"]) + 1, **color})
            if len(output["colors"]) >= int(settings["max_colors"]):
                break
        output["coverage"] = sum(c["share"] for c in output["colors"])
        output["defined"] = bool(output["colors"])
        return output



class WarmCoolDistributionExtractor(BaseExtractor):
    code = "warm_cool_distribution"
    method = "Configured CIELAB hue-angle warm/cool proxy over chromatic pixels"
    standard = "CIELAB hue angle h*ab; configured hue sectors"

    def extract(self, image, config):
        color_settings = config["color_analysis"]
        settings = color_settings["warm_cool"]

        chroma = _lab_chroma(image.lab)
        hue = _lab_hue_degrees(image.lab)

        floor = float(
            color_settings["achromatic_chroma_floor"]
        )

        chromatic = chroma >= floor

        if not np.any(chromatic):
            return {
                "defined": False,
                "achromatic_share": 1.0,
                "warm_share_of_chromatic": 0.0,
                "cool_share_of_chromatic": 0.0,
                "warm_weighted_share": 0.0,
                "cool_weighted_share": 0.0,
            }

        selected_hue = hue[chromatic]
        selected_chroma = chroma[chromatic]

        warm = _angle_in_ranges(
            selected_hue,
            settings["warm_ranges_degrees"],
        )

        cool = _angle_in_ranges(
            selected_hue,
            settings["cool_ranges_degrees"],
        )

        total_count = len(selected_hue)
        total_weight = selected_chroma.sum()

        return {
            "defined": True,
            "achromatic_share": float((~chromatic).mean()),
            "warm_share_of_chromatic": float(
                warm.sum() / total_count
            ),
            "cool_share_of_chromatic": float(
                cool.sum() / total_count
            ),
            "warm_weighted_share": float(
                selected_chroma[warm].sum() / total_weight
            ),
            "cool_weighted_share": float(
                selected_chroma[cool].sum() / total_weight
            ),
        }

class PaletteColorContrastExtractor(BaseExtractor):
    code = "palette_color_contrast"
    method = "Pairwise perceptual distance between dominant palette colours"
    standard = "CIEDE2000"

    def extract(self, image, config):
        palette = _dominant_palette(image, config)
        colors = palette["colors"]

        if len(colors) < 2:
            return {
                "defined": False,
                "pair_count": 0,
                "mean_delta_e2000": 0.0,
                "max_delta_e2000": 0.0,
                "pairs": [],
            }

        pairs: list[dict[str, Any]] = []
        distances: list[float] = []

        for i in range(len(colors)):
            for j in range(i + 1, len(colors)):
                first = np.array(
                    colors[i]["lab"],
                    dtype=np.float64,
                ).reshape(1, 1, 3)

                second = np.array(
                    colors[j]["lab"],
                    dtype=np.float64,
                ).reshape(1, 1, 3)

                distance = float(
                    deltaE_ciede2000(first, second)[0, 0]
                )

                distances.append(distance)

                pairs.append({
                    "first_rank": colors[i]["rank"],
                    "second_rank": colors[j]["rank"],
                    "first_hex": colors[i]["hex_srgb"],
                    "second_hex": colors[j]["hex_srgb"],
                    "delta_e2000": distance,
                })

        return {
            "defined": True,
            "pair_count": len(distances),
            "mean_delta_e2000": float(np.mean(distances)),
            "max_delta_e2000": float(np.max(distances)),
            "pairs": pairs,
        }

class ColorfulnessExtractor(BaseExtractor):
    code = "image_colorfulness"
    method = "Hasler-Susstrunk image colorfulness metric"
    standard = "Hasler and Susstrunk (2003)"

    def extract(self, image, config):
        rgb = image.srgb * 255.0

        red = rgb[..., 0]
        green = rgb[..., 1]
        blue = rgb[..., 2]

        rg = red - green
        yb = 0.5 * (red + green) - blue

        std_root = np.sqrt(
            rg.std() ** 2 +
            yb.std() ** 2
        )

        mean_root = np.sqrt(
            rg.mean() ** 2 +
            yb.mean() ** 2
        )

        colorfulness = std_root + 0.3 * mean_root

        return {
            "colorfulness": float(colorfulness),
            "rg_standard_deviation": float(rg.std()),
            "yb_standard_deviation": float(yb.std()),
            "rg_mean": float(rg.mean()),
            "yb_mean": float(yb.mean()),
        }


def _spatial_maps(
    image: NormalizedImage,
    config: dict[str, Any],
) -> dict[str, np.ndarray | float]:
    settings = config["space_analysis"]
    luminance = image.luminance
    gradient_y = (
        np.gradient(luminance, axis=0)
        if image.height > 1
        else np.zeros_like(luminance)
    )
    gradient_x = (
        np.gradient(luminance, axis=1)
        if image.width > 1
        else np.zeros_like(luminance)
    )
    gradient = np.hypot(gradient_x, gradient_y)
    sigma = max(
        float(settings["minimum_sigma_pixels"]),
        float(settings["local_window_fraction"])
        * min(image.width, image.height),
    )
    local_mean = gaussian_filter(
        luminance,
        sigma=sigma,
        mode=settings["boundary_mode"],
    )
    local_second_moment = gaussian_filter(
        luminance**2,
        sigma=sigma,
        mode=settings["boundary_mode"],
    )
    local_std = np.sqrt(
        np.maximum(local_second_moment - local_mean**2, 0.0)
    )
    low_information = (
        gradient
        <= float(settings["low_information_gradient_max"])
    ) & (
        local_std
        <= float(settings["low_information_local_std_max"])
    )
    return {
        "gradient": gradient,
        "local_std": local_std,
        "low_information": low_information,
        "sigma_pixels": sigma,
    }


def _focus_signal(
    image: NormalizedImage,
    config: dict[str, Any],
) -> np.ndarray:
    settings = config["space_analysis"]
    minimum_dimension = min(image.width, image.height)
    inner_sigma = max(
        float(settings["minimum_sigma_pixels"]),
        float(settings["focus_inner_sigma_fraction"])
        * minimum_dimension,
    )
    outer_sigma = max(
        inner_sigma,
        float(settings["focus_outer_sigma_fraction"])
        * minimum_dimension,
    )
    inner = gaussian_filter(
        image.luminance,
        sigma=inner_sigma,
        mode=settings["boundary_mode"],
    )
    outer = gaussian_filter(
        image.luminance,
        sigma=outer_sigma,
        mode=settings["boundary_mode"],
    )
    return np.abs(inner - outer)


class SpaceStructureExtractor(BaseExtractor):
    code = "space_structure"
    method = "Edge/texture information density and image-relative focus-gradient cues"
    standard = "Deterministic image-space proxy; no semantic depth or segmentation claim"

    def extract(self, image, config):
        settings = config["space_analysis"]
        maps = _spatial_maps(image, config)
        gradient = maps["gradient"]
        local_std = maps["local_std"]
        low_information = maps["low_information"]

        edge_density = float(
            np.mean(
                gradient
                >= float(settings["edge_magnitude_threshold"])
            )
        )
        texture_variation = float(np.mean(local_std))
        edge_component = float(
            np.clip(
                edge_density
                / float(settings["edge_density_reference"]),
                0.0,
                1.0,
            )
        )
        texture_component = float(
            np.clip(
                texture_variation
                / float(settings["texture_variation_reference"]),
                0.0,
                1.0,
            )
        )
        edge_weight = float(settings["complexity_edge_weight"])
        texture_weight = float(
            settings["complexity_texture_weight"]
        )
        complexity = (
            edge_component * edge_weight
            + texture_component * texture_weight
        ) / (edge_weight + texture_weight)

        focus = _focus_signal(image, config)
        yy, xx = np.indices(focus.shape)
        center_fraction = float(settings["center_region_fraction"])
        center = (
            np.abs((xx + 0.5) / image.width - 0.5)
            <= center_fraction / 2.0
        ) & (
            np.abs((yy + 0.5) / image.height - 0.5)
            <= center_fraction / 2.0
        )
        center_focus = float(np.mean(focus[center]))
        surround_focus = (
            float(np.mean(focus[~center]))
            if np.any(~center)
            else center_focus
        )
        focus_peak = max(center_focus, surround_focus)
        focus_separation = (
            abs(center_focus - surround_focus) / focus_peak
            if focus_peak > 0.0
            else 0.0
        )
        focus_reliable = (
            focus_peak >= float(settings["focus_signal_floor"])
            and focus_separation
            >= float(settings["focus_separation_min"])
        )
        foreground_background_hint = {
            "status": "available" if focus_reliable else "uncertain",
            "hint": (
                "center_sharper_than_surround"
                if focus_reliable and center_focus > surround_focus
                else "surround_sharper_than_center"
                if focus_reliable
                else "undetermined"
            ),
            "center_focus_signal": center_focus,
            "surround_focus_signal": surround_focus,
            "relative_separation": focus_separation,
            "uncertainty": (
                None
                if focus_reliable
                else "no_reliable_focus_separation"
            ),
        }

        band_count = min(int(settings["depth_band_count"]), image.height)
        band_names = [
            "top",
            "middle",
            "bottom",
        ] if band_count == 3 else [f"band_{index + 1}" for index in range(band_count)]
        band_values = [
            float(np.mean(part))
            for part in np.array_split(focus, band_count, axis=0)
        ]
        maximum_band = max(band_values)
        relative_spread = (
            (maximum_band - min(band_values)) / maximum_band
            if maximum_band > 0.0
            else 0.0
        )
        depth_reliable = (
            maximum_band >= float(settings["focus_signal_floor"])
            and relative_spread
            >= float(settings["depth_relative_spread_min"])
        )
        depth_layer_hint = {
            "status": "available" if depth_reliable else "uncertain",
            "hint": (
                "vertical_focus_gradient_detected"
                if depth_reliable
                else "undetermined"
            ),
            "sharpest_band": (
                band_names[int(np.argmax(band_values))]
                if depth_reliable
                else None
            ),
            "band_focus_signal": dict(zip(band_names, band_values)),
            "relative_spread": relative_spread,
            "uncertainty": (
                None
                if depth_reliable
                else "no_reliable_vertical_focus_gradient"
            ),
        }

        return {
            "configuration_version": settings["version"],
            "spatial_complexity": {
                "score": float(complexity),
                "edge_density": edge_density,
                "texture_variation": texture_variation,
                "edge_component": edge_component,
                "texture_component": texture_component,
            },
            "foreground_background_hint": foreground_background_hint,
            "depth_layer_hint": depth_layer_hint,
            "empty_space_ratio": float(np.mean(low_information)),
            "interpretation_limit": "Image-space cues only; not semantic foreground/background identity or physical depth",
        }


def _composition_saliency(image, config, maps=None):
    """Shared existing luminance-gradient/texture proxy; no semantic saliency model."""
    settings = config["composition_analysis"]
    maps = _spatial_maps(image, config) if maps is None else maps
    saliency = (np.asarray(maps["gradient"]) * float(settings["saliency_gradient_weight"])
                + np.asarray(maps["local_std"]) * float(settings["saliency_texture_weight"]))
    sigma = max(float(config["space_analysis"]["minimum_sigma_pixels"]),
                float(settings["saliency_smoothing_fraction"]) * min(image.width, image.height))
    return gaussian_filter(saliency, sigma=sigma, mode=config["space_analysis"]["boundary_mode"])


class CompositionGeometryExtractor(BaseExtractor):
    code = "composition_geometry"
    method = "Gradient/texture saliency centroid, low-information occupancy, and mirror similarity"
    standard = "Deterministic image-space proxy; no aesthetic or emotional judgment"

    def extract(self, image, config):
        settings = config["composition_analysis"]
        maps = _spatial_maps(image, config)
        saliency = _composition_saliency(image, config, maps)
        saliency_total = float(np.sum(saliency))
        saliency_mean = float(np.mean(saliency))
        peak_to_mean = (
            float(np.max(saliency)) / saliency_mean
            if saliency_mean > 0.0
            else 0.0
        )
        reliable = (
            saliency_mean
            >= float(settings["saliency_signal_floor"])
            and peak_to_mean
            >= float(settings["saliency_peak_to_mean_min"])
        )

        if reliable:
            yy, xx = np.indices(saliency.shape)
            center_x = float(
                np.sum(((xx + 0.5) / image.width) * saliency)
                / saliency_total
            )
            center_y = float(
                np.sum(((yy + 0.5) / image.height) * saliency)
                / saliency_total
            )
            lower = float(settings["position_center_min"])
            upper = float(settings["position_center_max"])
            horizontal = (
                "left" if center_x < lower else "right" if center_x > upper else "center"
            )
            vertical = (
                "upper" if center_y < lower else "lower" if center_y > upper else "middle"
            )
            subject_hint = {
                "status": "available",
                "horizontal": horizontal,
                "vertical": vertical,
                "hint": f"{vertical}_{horizontal}",
                "uncertainty": None,
            }
            offset_x = center_x - 0.5
            offset_y = center_y - 0.5
            center_offset = {
                "status": "available",
                "visual_center": [center_x, center_y],
                "x_offset": offset_x,
                "y_offset": offset_y,
                "normalized_distance": float(
                    np.hypot(offset_x, offset_y) / np.hypot(0.5, 0.5)
                ),
                "uncertainty": None,
            }
            thirds = np.asarray(
                settings["rule_of_thirds_points"],
                dtype=np.float64,
            )
            distances = np.hypot(
                thirds[:, 0] - center_x,
                thirds[:, 1] - center_y,
            )
            nearest_index = int(np.argmin(distances))
            nearest_distance = float(distances[nearest_index])
            distance_scale = float(
                settings["rule_of_thirds_distance_scale"]
            )
            thirds_result = {
                "status": "available",
                "score": float(
                    np.exp(-0.5 * (nearest_distance / distance_scale) ** 2)
                ),
                "nearest_intersection": thirds[nearest_index].tolist(),
                "normalized_distance": nearest_distance,
                "uncertainty": None,
            }
        else:
            subject_hint = {
                "status": "uncertain",
                "horizontal": None,
                "vertical": None,
                "hint": "undetermined",
                "uncertainty": "no_reliable_salient_region",
            }
            center_offset = {
                "status": "uncertain",
                "visual_center": None,
                "x_offset": None,
                "y_offset": None,
                "normalized_distance": None,
                "uncertainty": "no_reliable_salient_region",
            }
            thirds_result = {
                "status": "uncertain",
                "score": None,
                "nearest_intersection": None,
                "normalized_distance": None,
                "uncertainty": "no_reliable_salient_region",
            }

        luminance = image.luminance
        half_width = image.width // 2
        half_height = image.height // 2
        left_right = (
            float(
                1.0
                - np.mean(
                    np.abs(
                        luminance[:, :half_width]
                        - np.flip(luminance[:, -half_width:], axis=1)
                    )
                )
            )
            if half_width > 0
            else 1.0
        )
        top_bottom = (
            float(
                1.0
                - np.mean(
                    np.abs(
                        luminance[:half_height, :]
                        - np.flip(luminance[-half_height:, :], axis=0)
                    )
                )
            )
            if half_height > 0
            else 1.0
        )

        return {
            "configuration_version": settings["version"],
            "subject_position_hint": subject_hint,
            "visual_center_offset": center_offset,
            "negative_space_ratio": float(
                np.mean(maps["low_information"])
            ),
            "symmetry_score": {
                "left_right": left_right,
                "top_bottom": top_bottom,
                "mean": (left_right + top_bottom) / 2.0,
            },
            "rule_of_thirds_score": thirds_result,
            "saliency_diagnostics": {
                "peak_to_mean": peak_to_mean,
                "mean_signal": saliency_mean,
            },
            "interpretation_limit": "Computed geometry and saliency hints only; not an aesthetic judgment",
        }




class GlobalToneExtractor(BaseExtractor):
    code, method = "global_tonal_contrast", "Spread descriptors over CIELAB L*"
    def extract(self, image, config):
        p5, p25, p75, p95 = np.percentile(image.lightness, [5, 25, 75, 95])
        return {"lstar_p95_p05_span": float(p95-p5), "lstar_iqr": float(p75-p25), "lstar_standard_deviation": float(image.lightness.std())}

class TonalOccupancyExtractor(BaseExtractor):
    code = "tonal_occupancy"
    method = "Configured operational low-, mid-, and high-lightness bins over CIELAB L*"
    standard = "CIELAB L* D65/2-degree; application-defined versioned bin boundaries"

    def extract(self, image, config):
        settings = config["tonal_occupancy"]

        shadow_max = float(settings["shadow_lstar_max"])
        highlight_min = float(settings["highlight_lstar_min"])

        if shadow_max >= highlight_min:
            raise ValueError(
                "shadow_lstar_max must be lower than highlight_lstar_min"
            )

        lightness = image.lightness

        shadow = lightness <= shadow_max
        highlight = lightness >= highlight_min
        midtone = (~shadow) & (~highlight)

        return {
            "configuration_version": settings["version"],
            "measurement_space": settings["space"],
            "boundary_policy": settings["boundary_policy"],
            "shadow_lstar_max": shadow_max,
            "highlight_lstar_min": highlight_min,
            "shadow_share": float(shadow.mean()),
            "midtone_share": float(midtone.mean()),
            "highlight_share": float(highlight.mean()),
            "occupancy_sum": float(shadow.mean() + midtone.mean() + highlight.mean()),
            "interpretation_limit": "Operational tone bins only; not semantic shadows/highlights or exposure quality",
        }

class LocalContrastExtractor(BaseExtractor):
    code, method, standard = "multiscale_local_contrast", "Peli-style Gaussian center-surround contrast normalized by local adaptation", "Peli (1990), adapted Gaussian implementation"
    def extract(self, image, config):
        settings, output = config["local_contrast"], []
        for fraction in settings["scale_fractions"]:
            sigma = max(0.5, float(fraction) * min(image.width, image.height))
            center = gaussian_filter(image.luminance, sigma=sigma, mode=settings["boundary_mode"])
            surround = gaussian_filter(image.luminance, sigma=sigma * float(settings["surround_ratio"]), mode=settings["boundary_mode"])
            contrast = np.abs(center-surround) / np.maximum(surround, float(settings["denominator_floor"]))
            output.append({"scale_fraction": fraction, "sigma_pixels": sigma, "energy_rms": float(np.sqrt(np.mean(contrast**2))), "median": float(np.median(contrast)), "p90": float(np.percentile(contrast, 90))})
        return {"scales": output}


class EndpointExtractor(BaseExtractor):
    code, method = "source_endpoint_occupancy", "Exact source-code black and white occupancy before colour conversion"
    def extract(self, image, config):
        if image.source_black_occupancy is None: raise ValueError("ENDPOINT_OCCUPANCY_NOT_MEANINGFUL_FOR_SOURCE_MODE")
        return {"exact_black_occupancy": image.source_black_occupancy, "exact_white_occupancy": image.source_white_occupancy}


class ExtractorRegistry:
    def __init__(self, extractors: list[VisualFeatureExtractor] | None = None):
        self.extractors = extractors or [
            MetadataExtractor(),
            LuminanceExtractor(),
            LightnessExtractor(),

            ChromaExtractor(),
            ChromaticOccupancyExtractor(),
            HueDistributionExtractor(),
            DominantPaletteExtractor(),
            AccentPaletteExtractor(),
            WarmCoolDistributionExtractor(),
            PaletteColorContrastExtractor(),
            ColorfulnessExtractor(),

            SpaceStructureExtractor(),
            CompositionGeometryExtractor(),

            GlobalToneExtractor(),
            LocalContrastExtractor(),
            EndpointExtractor(),
            TonalOccupancyExtractor(),
        ]

    def run(self, image: NormalizedImage, config: dict[str, Any]) -> list[FeatureResult]:
        results: list[FeatureResult] = []
        for extractor in self.extractors:
            common = {"extractor_code": extractor.code, "extractor_version": extractor.version, "feature_schema_version": extractor.schema_version, "method": extractor.method, "standard": extractor.standard, "parameters": config, "provenance": image.provenance, "warnings": list(image.warnings)}
            try: results.append(FeatureResult(**common, status="succeeded", values=extractor.extract(image, config)))
            except Exception as exc: results.append(FeatureResult(**common, status="failed", error_detail=f"{type(exc).__name__}: {exc}"))
        return results
