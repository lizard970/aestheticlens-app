from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any, Protocol

import numpy as np
import PIL
import scipy
import skimage
from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError
from scipy.ndimage import gaussian_filter
from skimage.color import rgb2lab, rgb2xyz, xyz2rgb

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
    return NormalizedImage(source_size[0], source_size[1], rgb.width, rgb.height, source_format, source_mode, profile_source, profile_assumed, alpha_present, xyz[..., 1], lab[..., 0], black, white, warnings, provenance)


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


class GlobalToneExtractor(BaseExtractor):
    code, method = "global_tonal_contrast", "Spread descriptors over CIELAB L*"
    def extract(self, image, config):
        p5, p25, p75, p95 = np.percentile(image.lightness, [5, 25, 75, 95])
        return {"lstar_p95_p05_span": float(p95-p5), "lstar_iqr": float(p75-p25), "lstar_standard_deviation": float(image.lightness.std())}


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
        self.extractors = extractors or [MetadataExtractor(), LuminanceExtractor(), LightnessExtractor(), GlobalToneExtractor(), LocalContrastExtractor(), EndpointExtractor()]

    def run(self, image: NormalizedImage, config: dict[str, Any]) -> list[FeatureResult]:
        results: list[FeatureResult] = []
        for extractor in self.extractors:
            common = {"extractor_code": extractor.code, "extractor_version": extractor.version, "feature_schema_version": extractor.schema_version, "method": extractor.method, "standard": extractor.standard, "parameters": config, "provenance": image.provenance, "warnings": list(image.warnings)}
            try: results.append(FeatureResult(**common, status="succeeded", values=extractor.extract(image, config)))
            except Exception as exc: results.append(FeatureResult(**common, status="failed", error_detail=f"{type(exc).__name__}: {exc}"))
        return results
