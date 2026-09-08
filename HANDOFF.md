# Codex Handoff

## Stage 1C-01 operator-approved implementation (2026-09-09)

This instruction supersedes earlier Mock-only restrictions for semantics. Implemented on `feat/20260907-next`; local commit only, no push or deployment.

- Existing orchestration injects Mock or configurable Chat Completions multimodal adapters. No public result schema, feature algorithm, database, or route changes.
- Normalized PNG and successful feature references feed all five dimensions. Versioned Prompt, strict output Schema and editable style vocabulary validate dimensions, tags, leaf references and numeric placeholders. Explicit uncertainty and mixed/no-style selections are supported.
- Timeout and bounded transient retries retain per-attempt usage, duration, versions and sanitized errors in existing provenance; unknown cost remains null. Model failure preserves real calculations and returns partial, never silently Mock.
- Frontend derives pipeline and semantic labels from provenance, displays failures/uncertainty/style tags, and removes probability-like confidence presentation.
- Offline HTTP transport blocking prevents test model charges. `backend: python -m pytest -q`: 48 passed. `pnpm test`: 10 passed. `pnpm typecheck` and `pnpm build`: passed. Targeted `pnpm exec oxlint` over changed TS/TSX files: passed. `pnpm lint`: 20 existing findings in unmodified UI-kit, hook and webmcp files; not expanded into this task.
- No live provider/base URL/model/API key is configured; offline passed, live invocation pending. Configure `.env` using `.env.example` and follow `docs/stage-1c-01.md`. No new dependency was needed.

## Goal

Implement Stage 1B-01 for AestheticLens: replace the Stage 1A mock computational feature values with a real, colour-managed, deterministic single-image tone and contrast measurement pipeline, while preserving the existing API, task lifecycle, mock semantic analysis, and all future extension boundaries.

The implemented pipeline must measure observable image properties only. It must not claim to measure absolute human-perceived brightness, aesthetic quality, correct exposure, or semantic shadow/highlight regions without the viewing conditions or validated model/annotation data required for those claims.

## Current Context

- Stage 1A is reported by the user as working end to end: image upload, API-driven capabilities and analysis profile, task states, explicitly labelled mock analysis, feedback flow, and refresh/recovery behavior.
- The product baseline is `aestheticlens_product_report_v0.1.md`. Section 15 is authoritative: Stage 1B introduces real computational image features. Section 19 is stale where it says the next stage is 1A; 1A is already complete.
- The product separates three layers:
  1. deterministic/computational facts;
  2. model-generated visual semantics;
  3. composite aesthetic judgments.
- This ticket implements only the first layer for SDR still images.
- The current web environment could not inspect the repository code. Before editing, inspect the repository structure, current 1A contracts, package manifests, tests, and existing commands. Adapt the implementation to the existing architecture instead of inventing a parallel stack.
- Supported input scope for this ticket: valid SDR JPG/JPEG, PNG, and WebP images within the existing configured media limits.
- Scientific/technical baseline:
  - ICC colour management / ISO 22028 architecture for consistent interpretation across source colour spaces.
  - ISO/CIE 11664-4 CIELAB `L*` as an approximate perceptual-lightness correlate with an explicit reference white.
  - Relative luminance `Y` derived only after decoding the source transfer function / colour profile into a linear-light representation.
  - Peli (1990), "Contrast in complex images", for band-limited local contrast in complex natural images.
- Important terminology:
  - UI copy should say `relative luminance` and `perceptual lightness`, not a generic `brightness percentage`.
  - `Contrast` is not one universal scalar. Preserve global tonal distribution and multiscale local contrast as separate feature families.
  - Percentile statistics are descriptive measurements, not claims that one exposure or aesthetic is correct.

## Decisions Already Made

1. Preserve the existing `/api/v1` resources, job state machine, idempotency behavior, response schema/version strategy, Adapter boundaries, and refresh/recovery behavior from Stage 1A.
2. Keep the existing five-dimension semantic/aesthetic analysis on the explicitly labelled Mock adapter. Do not make mock semantic results appear real because real low-level features now exist.
3. Introduce independently registered and independently testable feature extractors. A failed extractor must not erase successful extractor results; the run/job must expose the existing partial-success state and warning/error metadata.
4. Use established colour-management libraries already compatible with the repository. Prefer an ICC engine backed by LittleCMS (for example Pillow `ImageCms`) plus a well-tested colour-science implementation. Do not implement ICC transforms, transfer curves, CIELAB, or chromatic adaptation from scratch unless the repository already contains a rigorously tested implementation.
5. Processing order is fixed:
   - verify file signature and decode the image;
   - apply EXIF orientation before reporting dimensions or spatial measurements;
   - inspect image mode, bit depth, ICC profile, PNG colour chunks where available, and alpha;
   - transform supported source colour encodings into an explicitly recorded SDR working representation;
   - create a linear-light representation for relative luminance calculations;
   - compute CIELAB `L*` with the declared reference white;
   - run feature extractors;
   - return values, warnings, artifacts, parameters, and provenance.
6. Embedded ICC information takes precedence. If no usable profile exists, apply the documented format/default interpretation used by the chosen standards/library and set `profile_assumed=true`. Never silently label an assumed profile as embedded or verified.
7. Do not silently tone-map HDR/WCG inputs into SDR. If the current library cannot unambiguously decode and transform an encoding, return a stable unsupported-colour-encoding error or a partial result according to the existing job contract. Preserve enough metadata for a later HDR path.
8. Alpha has no intrinsic displayed colour. Add/configure `display_background` through the versioned analysis profile. Composite in an explicitly declared compositing space, record background and method in provenance, and output alpha coverage. Do not bury a white-background constant in extractor code.
9. If an analysis raster is resized for memory/performance, the canonical sizing rule, resampler, original dimensions, analysis dimensions, and scale normalization must be versioned and recorded. Multiscale measurements must use scales relative to image dimensions or a documented canonical raster; raw pixel scale must not make the same picture materially different only because it was exported at a larger resolution.
10. Implement these real feature families:

### A. Image metadata and normalization provenance

- original and orientation-corrected width/height;
- format, decoded mode, bit depth where available;
- alpha presence and alpha coverage;
- embedded/assumed source colour profile identifier;
- working colour space, reference white, transform/library version;
- original and analysis raster dimensions;
- resize/resampling metadata when applicable;
- warnings for missing/invalid profiles or unsupported encodings.

### B. Tone distribution

Maintain both representations; do not collapse them into one `brightness` field.

- Linear relative luminance `Y` distribution: mean, median, p01, p05, p25, p75, p95, p99, and a versioned histogram.
- CIELAB perceptual lightness `L*` distribution: mean, median, p01, p05, p25, p75, p95, p99, and a versioned histogram.
- Histogram binning/range must be declared in extractor configuration and returned in provenance.

### C. Global tonal contrast descriptors

- robust lightness span: `L*_p95 - L*_p05`;
- interquartile range: `L*_p75 - L*_p25`;
- `L*` standard deviation;
- retain the full/versioned lightness histogram.

These are separate statistical descriptors. Do not label any one of them as the definitive human-perceived contrast score.

### D. Multiscale local contrast

- Implement a documented Peli-style band-limited local contrast extractor using a Gaussian/Laplacian or equivalent band-pass pyramid and local adaptation luminance.
- Return per-scale results rather than prematurely reducing the result to one scalar.
- At each scale, return at minimum a contrast-energy statistic plus robust distribution summaries such as median and p90, and optionally a map artifact if the existing artifact boundary supports it.
- Scale schedule, boundary handling, normalization denominator/floor, aggregation, and any masking rules must be explicit, versioned configuration with justification in code/docs. No unexplained magic numbers.
- Without physical display size, viewing distance, and ambient illumination, describe these as image-relative spatial scales, not cycles-per-degree human-vision measurements.

### E. Objective endpoint and tail diagnostics

- output exact encoded/source black-end and white-end occupancy when the source representation makes this meaningful;
- output tone-distribution tails through the percentiles above;
- do not output `shadow_ratio` or `highlight_ratio` based on arbitrary fixed thresholds such as 0.2 and 0.8;
- do not infer `correct exposure`, `underexposed`, `overexposed`, semantic shadows, or semantic highlights in this deterministic ticket.

11. Every FeatureResult must expose or map cleanly to the existing result contract with:
   - extractor code and version;
   - method/standard identifier;
   - feature-schema version;
   - parameters actually used;
   - values and artifact references;
   - status and error detail;
   - working colour representation;
   - provenance/warnings.
12. All configurable thresholds, histogram bins, raster limits, alpha background, pyramid scales, and numerical safeguards belong in the versioned analysis/feature-extractor configuration. Standards-defined equations and constants may be implemented in code but must cite/name the standard and be protected by conformance tests.
13. Frontend feature cards must clearly distinguish `Real computation` from `Mock semantic analysis`.
14. Each frontend metric explanation must contain:
   - a precise plain-language definition;
   - why the metric is useful;
   - one very simple example understandable without image-processing knowledge.

Example copy pattern:

- Global tonal span: "This shows how far apart the commonly used dark and light tones are. Imagine two bowls: one contains only gray beans, and the other contains half black and half white beans. Their average can look similar, but the second bowl uses a much wider light-to-dark range."
- Multiscale local contrast: "This shows the size of the light-dark patterns. A picture split into a black half and a white half has one large light-dark division. A black-white checkerboard has many tiny divisions. Their black/white counts can be identical, but the pattern sizes are different."

15. Learned exposure assessment (including P-IEANet-like models), CAM16 brightness under explicit viewing conditions, colour features, aesthetic scoring, semantic shadow/highlight segmentation, and video processing are separate future extractors/tickets. Do not smuggle them into this deterministic baseline.

## Required Changes

1. Inspect the existing Stage 1A implementation and document in the final Codex report which existing interfaces/classes/routes/components are being reused.
2. Add the minimum dependencies required for robust decode, ICC-aware conversion, numerical processing, and multiscale filtering. Pin them according to the repository's existing dependency policy and verify licence compatibility. Avoid duplicate libraries that solve the same problem.
3. Implement or complete the image-ingestion/normalization adapter described above.
4. Implement a feature-extractor interface/registry only if the existing domain boundary does not already provide it. Reuse the baseline `VisualFeatureExtractor` concept and keep infrastructure libraries out of the domain layer.
5. Implement separate extractors/results for:
   - image metadata/normalization provenance;
   - linear relative-luminance distribution;
   - CIELAB `L*` distribution;
   - global tonal-contrast descriptors;
   - Peli-style multiscale local contrast;
   - objective endpoint occupancy/diagnostics where meaningful.
6. Wire real extractor outputs into the existing analysis pipeline and result response without breaking Stage 1A API behavior.
7. Preserve successful results when one extractor raises a controlled failure; surface the extractor error and partial status through existing job/run/result structures.
8. Update the existing frontend computational-feature section to render real values, method/version/provenance, warnings, and plain-language explanations/examples. Keep semantic sections visibly Mock.
9. Add fixtures/tests that differentiate distribution from spatial structure:
   - all black;
   - all white;
   - uniform mid-gray;
   - half black/half white split;
   - black/white checkerboard with the same pixel proportions as the split image;
   - smooth black-to-white gradient;
   - valid ICC-tagged sRGB image;
   - two colour-managed encodings intended to render equivalently, if fixture creation is reliable;
   - EXIF-rotated image;
   - transparent image with configured background;
   - missing/invalid ICC profile;
   - corrupted image bytes;
   - unsupported/HDR encoding where a stable fixture is available;
   - one deliberately failing extractor.
10. Assert mathematical invariants and reference values with justified numerical tolerances rather than vague snapshots:
    - uniform images have zero/negligible global spread and zero/negligible multiscale contrast;
    - split and checkerboard images have comparable histograms/global tonal descriptors but different per-scale local-contrast signatures;
    - black, white, and gray fixtures produce CIELAB/relative-luminance values matching an independent trusted implementation within tolerance;
    - EXIF orientation changes reported dimensions correctly;
    - colour-managed equivalent fixtures produce equivalent results within tolerance;
    - alpha-background changes are explicit and reproducible;
    - a failed extractor yields partial status while successful extractor results remain accessible.
11. Add concise technical documentation inside the repository covering equations/methods, reference white, transfer-function handling, colour assumptions, Peli implementation choices, numerical safeguards, known limitations, and citations.
12. Run the repository's existing backend/frontend test, lint, type-check, and build commands. Do not rename or reorganize unrelated files merely to fit this task.

## Do Not Change

- Do not modify `main` directly.
- Do not redesign the Stage 1A UI or navigation.
- Do not change stable `/api/v1` resource semantics, task statuses, idempotency behavior, or future endpoint paths.
- Do not replace the existing architecture with a second framework or parallel pipeline.
- Do not remove the Mock semantic analyzer; keep it clearly labelled.
- Do not add a total aesthetic score.
- Do not add multimodal model/API credentials.
- Do not implement colour palette, saturation, colour temperature, composition, saliency, object detection, semantic shadows/highlights, learned exposure quality, knowledge retrieval, embeddings, RAG, video/frame extraction, database migration, or production object storage in this ticket unless a tiny compatibility change is strictly required by the existing contract.
- Do not silently assume all files are sRGB, silently discard ICC profiles, apply transfer-function coefficients to gamma-encoded data as if it were linear, silently flatten alpha to white, or silently tone-map HDR.
- Do not use the obsolete arbitrary `Y < 0.2` / `Y > 0.8` thresholds.
- Do not present percentile ranges, standard deviation, Peli-band outputs, or endpoint occupancy as an objective measure of beauty or correct exposure.
- Do not hardcode adjustable business/science parameters inside controllers or React components.
- Do not invent numerical claims when the source viewing conditions are unknown.

## Acceptance Criteria

1. A real supported SDR JPG, PNG, or WebP is decoded, orientation-corrected, colour-managed, analyzed, and displayed using real computed values.
2. Results include sufficient provenance to reproduce the transform and every extractor: source/assumed profile, working colour representation, reference white, extractor/schema version, actual parameters, library version, and analysis raster dimensions.
3. Linear relative-luminance and CIELAB `L*` distributions are both available and are not conflated under one generic brightness score.
4. Global tonal descriptors and per-scale local-contrast descriptors are both available and clearly distinguished.
5. The split black/white image and same-proportion checkerboard demonstrate the same/comparable global tone distribution but different spatial-scale contrast results.
6. No arbitrary shadow/highlight area ratio is emitted. Endpoint occupancy and distribution tails are named accurately.
7. Transparent inputs use the versioned configured background and expose alpha/compositing provenance.
8. Missing/invalid profile, corrupted input, unsupported encoding, and individual extractor failure produce stable warnings/errors and never an empty fake success.
9. One extractor failure preserves all successful feature results and produces the existing partial-success state.
10. Existing Stage 1A upload, polling/recovery, mock semantic analysis, feedback, and capabilities/profile flows continue to pass.
11. Frontend labels real computational features and mock semantic analysis unambiguously.
12. Each displayed metric has an accurate plain-language definition, purpose, and simple concrete example.
13. Automated tests cover the fixtures and invariants in Required Changes and pass deterministically across supported development environments.
14. Backend tests, frontend tests, lint/type-check, and production build all pass.
15. Final Codex report lists files changed, methods/standards implemented, exact test commands/results, limitations, and any deliberate deviations from this handoff.

## Test Commands

First inspect the repository README, lockfiles, `pyproject.toml`/requirements files, `package.json`, and CI configuration. Use the repository's actual package manager and existing scripts. At minimum run the applicable equivalents of:

```bash
# Backend, from the repository's actual backend environment/directory
python -m pytest

# Frontend, from the actual frontend package directory
npm test -- --run
npm run lint
npm run typecheck
npm run build
```

If the repository uses `uv`, Poetry, pnpm, yarn, Turborepo, or different script names, use the lockfile/CI-defined commands instead and report the exact commands. Add focused extractor tests to the normal backend test suite; do not create a separate unmaintained test runner.

## Open Questions

None for product scope. Codex must resolve repository-specific file locations, dependency tooling, and existing test commands by inspecting the codebase before implementation. If the existing API cannot represent extractor provenance or partial feature results without a contract change, stop and report the exact mismatch before changing the public contract.

## Implementation Status

Implemented on `handoff/20260906-tone-contrast`. The public result contract was extended with operator approval: `JobStatus.partial`, defaulted feature/warning/completion fields, and `mock | hybrid | real` provenance modes. Real deterministic feature extraction is wired to the existing Stage 1A API and UI while semantic dimensions remain clearly Mock.

## Test Results

- Backend: `python -m pytest -q` — 17 passed (fixture/invariant suite plus Stage 1A API compatibility).
- Frontend type-check: `pnpm typecheck` — passed.
- Frontend changed-file lint: passed.
- Frontend production build: `pnpm build` — passed.
- Full `pnpm lint` still reports pre-existing generated UI-kit accessibility/compiler findings outside this ticket; changed files pass targeted lint.

## Stage 1B-03 operator-approved follow-up

The later operator instruction adds versioned, configurable CIELAB `L*` tonal occupancy (`shadow`, `midtone`, `highlight`) as an operational distribution for comparison and retrieval. This does not reinstate the prohibited arbitrary `Y < 0.2 / Y > 0.8` calculation and does not claim semantic shadows/highlights, correct exposure, low-key photography, or aesthetic quality. The old fake Evidence overlay is removed; real Evidence Builder work remains Stage 1D.

Validation on `feat/20260907-next`: backend 26 passed; frontend 3 passed; TypeScript and production build passed. Changed Stage 1B files pass targeted lint. Full-repository lint still reports pre-existing generated UI-kit accessibility/compiler findings outside the Stage 1B scope.

## Stage 1B space/composition completion

The later operator instruction extends the Stage 1B computational layer with independently registered `SpaceStructureExtractor` and `CompositionGeometryExtractor`. Both reuse the existing normalized SDR image and `FeatureResult` contract. They return deterministic edge, texture, focus-gradient, low-information, saliency-centroid, symmetry, and thirds-distance measurements; unreliable saliency or focus separation is explicitly returned as `uncertain`. No GPT, external model, persistence change, or aesthetic/emotional inference is introduced.

Validation on `feat/20260907-next`: backend 31 passed; frontend 6 passed; TypeScript, changed-file lint, Python compilation, and production build passed. Full-repository lint continues to report the documented pre-existing UI-kit/hook/declaration findings outside the Stage 1B change set.
