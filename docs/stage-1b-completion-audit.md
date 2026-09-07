# Stage 1B completion audit

## Feature workstream

| Slice | Result | Evidence |
| --- | --- | --- |
| 1B-01 tone and contrast | Complete | ICC/EXIF/alpha-aware normalization; relative luminance, CIELAB L*, global spread, multiscale local contrast, endpoint diagnostics |
| 1B-02 colour | Complete | Chroma, chromatic occupancy, hue distribution, deterministic palette, warm/cool distribution, CIEDE2000 palette contrast, colourfulness |
| 1B-03 lighting close-out | Complete | Versioned CIELAB L* tonal occupancy, three-level tone distribution UI, extractor/API/UI tests, obsolete Mock evidence overlay removed |
| 1B-04 space | Complete | Edge/texture complexity, low-information occupancy, focus separation and depth-layer hints with explicit uncertainty |
| 1B-05 composition | Complete | Saliency-centroid position, center offset, negative space, mirror symmetry and rule-of-thirds proximity |
| Extractor isolation and degradation | Complete | Registry-based extractors and `succeeded`/`failed` feature results; aggregate `complete`/`partial` status |

The current tonal bins are operational application labels: shadow `L* <= 20`, midtone `20 < L* < 80`, and highlight `L* >= 80`. They are configurable in `backend/config/analysis_profiles.json`, included in result provenance, and must not be presented as a CIE definition of semantic shadows/highlights, correct exposure, low-key photography, or aesthetic quality.

## Deliberately later boundaries

- Light-source direction needs spatial evidence or a validated model/rule and remains a Stage 1C concern.
- “High contrast” or “low-key” is not inferred automatically in Stage 1B; the measured features can become evidence for a later versioned rule or model.
- Evidence regions and conclusion-to-region links belong to the Stage 1D Evidence Builder. The obsolete fake overlay is removed rather than maintained.

## Infrastructure gaps in the original product baseline

The strict wording of product-report Stage 1B also names object storage, durable metadata, and run records. The current prototype only has an in-memory repository and job/result objects; idempotency is accepted but not durably enforced. Those are outside the operator-approved computational-feature scope and were intentionally not expanded. Therefore the computational-feature gate is ready for Stage 1C, while production persistence remains a separate engineering ticket before claiming the entire product-baseline Stage 1B is production-complete.
