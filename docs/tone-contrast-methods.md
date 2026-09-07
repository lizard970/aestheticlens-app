# Tone and contrast feature methods (Stage 1B-01)

This pipeline reports reproducible computational facts, not aesthetic quality or exposure correctness.

## Normalization

Pillow decodes JPG, PNG, and WebP and applies EXIF orientation. Embedded ICC profiles take precedence and are converted to sRGB through LittleCMS (`Pillow.ImageCms`). A missing profile is explicitly recorded as assumed sRGB; an invalid profile is warned and may only fall back for RGB/gray encodings. Integer/high-dynamic-range modes are rejected rather than silently tone-mapped. Oversized rasters use the configured, versioned Lanczos policy.

Alpha is composited against the configured display background in linear-light CIE XYZ D65. Measurements use CIE D65 with the 2° observer. `scikit-image` performs sRGB transfer decoding, XYZ conversion, and CIELAB conversion; the application does not duplicate those standard transforms.

## Extractors

- Relative luminance is the XYZ `Y` component after colour management and linear-light compositing. It reports mean, median, P01/P05/P25/P75/P95/P99, and a configured histogram on `[0,1]`.
- CIELAB lightness reports the same distribution fields for `L*` on `[0,100]`. It is not interchangeable with relative luminance.
- Global tonal contrast reports `L*(P95)-L*(P05)`, interquartile range, and population standard deviation.
- Multiscale local contrast uses Gaussian center/surround responses. For each configured image-relative scale, `C=|Gσ(Y)-G(rσ)(Y)| / max(G(rσ)(Y), ε)`. It reports RMS energy, median, and P90. Reflect boundaries and a configured denominator floor make the implementation deterministic.
- Endpoint diagnostics count only source-code pixels exactly black or white where the source mode makes this meaningful. They are not arbitrary “shadow/highlight” regions.
- Tonal occupancy divides CIELAB `L*` into versioned application bins (`L* <= 20`, `20 < L* < 80`, and `L* >= 80` by the current profile). These boundaries are configurable operational labels for comparison and retrieval, not a CIE definition of semantic shadows/highlights, correct exposure, or aesthetic quality.

Every feature carries extractor/schema versions, actual configuration, normalization provenance, library versions, warnings, and controlled errors. An extractor failure leaves successful sibling results available and makes the aggregate result partial.

## Limits

The pipeline is SDR-only, works on a single still image, and does not infer scene luminance, display brightness, exposure intent, semantic shadows, composition, colour temperature, or aesthetic quality. Missing-profile sRGB is an explicit assumption. Resampling is performed in colour-managed encoded sRGB before linear measurement. Peli-style outputs are an adapted engineering descriptor, not a perceptual threshold prediction under known viewing conditions.

## References and licences

- IEC 61966-2-1:1999, sRGB colour space.
- CIE 15:2018, Colorimetry; CIE 1976 L*a*b*.
- Peli, E. (1990), “Contrast in complex images,” *JOSA A*, 7(10), 2032–2040.
- Pillow (HPND), NumPy/SciPy/scikit-image (BSD-3-Clause). These permissive licences are compatible with this repository; no duplicate colour-management library is added.
