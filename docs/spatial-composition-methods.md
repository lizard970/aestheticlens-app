# Stage 1B space and composition methods

`SpaceStructureExtractor` and `CompositionGeometryExtractor` consume the same colour-managed, orientation-corrected SDR analysis raster as the existing lighting and colour extractors. They emit deterministic image measurements and hints through `FeatureResult`; they do not emit aesthetic, emotional, object, or scene-semantic judgments.

## Shared information maps

The extractors use linear-light relative luminance `Y`. Horizontal and vertical numerical gradients form a gradient-magnitude map. Local texture variation is the square root of a Gaussian-window variance:

`local_std = sqrt(max(G(Y²) - G(Y)², 0))`

A pixel is low-information only when both its gradient magnitude and local standard deviation are below the versioned profile limits. `empty_space_ratio` and composition `negative_space_ratio` are the occupancy of this same reproducible mask. They describe low visual information, not semantic emptiness.

`spatial_complexity.score` combines normalized edge density and mean local texture variation. Its thresholds, references, and weights are stored in `backend/config/analysis_profiles.json`.

## Focus and depth hints

An image-relative difference-of-Gaussians magnitude is used as a focus-detail signal. Center-versus-surround and top/middle/bottom comparisons are reported only when both the absolute signal and relative separation pass configured reliability limits. Otherwise the corresponding hint has `status=uncertain` and a machine-readable uncertainty reason. These outputs cannot identify physical distance, foreground objects, or background objects.

## Composition geometry

The saliency proxy is a configured weighted combination of gradient magnitude and local texture variation, followed by image-relative Gaussian smoothing. A weighted centroid is returned only when the mean signal and peak-to-mean ratio pass configured reliability limits.

- `subject_position_hint` bins the reliable centroid into configured horizontal and vertical regions.
- `visual_center_offset` is its Euclidean distance from image center, normalized by the center-to-corner distance.
- `symmetry_score` is one minus mean absolute luminance difference after horizontal or vertical mirror alignment.
- `rule_of_thirds_score` is a Gaussian distance score to the nearest configured thirds intersection.

All scores are descriptive proxies. A high or low value is not a claim that an image is beautiful, cinematic, lonely, oppressive, or compositionally correct.

## Known limits

- Edge/texture saliency can be attracted to patterned backgrounds and cannot replace subject detection.
- Blur gradients may come from motion, compression, denoising, or lens behavior rather than scene depth.
- Low-information occupancy is not semantic negative space.
- Mirror similarity is sensitive to exposure and texture differences even when semantic structure is symmetric.
