# Stage 1D and structured retrieval foundation

Baseline: `aestheticlens_product_report_v0.2.md`, limited to the operator's current single-image evidence/review/search slice. Feature extractors and multimodal adapter logic are unchanged.

## Evidence and original results

`GET /api/v1/analysis-jobs/{job_id}/result` and `GET /api/v1/analysis-results/{result_id}` retain all original analysis fields and add `evidence`, `human_revision`, `asset_id`, `preview_url`. Computed leaf references reuse `feature:<extractor_code>#/JSON/pointer` including escaped keys and array indices. Only successful stored feature values resolve. Duplicate references share one evidence object with `supports_dimensions`. Missing/failed refs are `invalid`; old `mock:` refs are explicitly Mock, never a fabricated metric. Labels come from `backend/config/evidence_labels.json`, falling back to extractor method and pointer.

Each dimension has an expandable Evidence panel with resolved labels/values. Existing extractors supply no real region coordinates, so this slice deliberately draws no image overlay. No coordinates are synthesized from saliency or dimension names.

## Append-only feedback

`POST /api/v1/analysis-results/{result_id}/feedback` accepts the existing accept/edit/reject/flag_error vocabulary. New UI actions are per dimension, with `target_path=/dimensions/<code>`; an edit supplies both `observation` and `interpretation` in `corrected_value`. Field paths ending `/observation` or `/interpretation` also accept text edits. Notes/error category are optional. Legacy whole-result accept/reject remains compatible.

Each record has a server-assigned result-local revision and original value; the stored analysis is never edited. `base_revision` is optional for legacy callers, supplied by the new UI and checked atomically to return `409 REVISION_CONFLICT` for stale writes. Editing confirms the revised dimension; accept confirms its current effective text; reject/flag_error marks it unconfirmed without erasing prior text. The UI labels model originals and human revisions separately. Original model evidence is not automatically asserted to support changed human claims.

- `GET /api/v1/analysis-results/{result_id}/feedback`: original result, ordered feedback records, latest reconstructed revision.
- `GET /api/v1/analysis-results/{result_id}?revision=N`: original plus state after revision N; zero is the untouched state.
- `GET /api/v1/analysis-results`: stored result history for the history picker.
- `GET /api/v1/assets/{asset_id}/content`: retained image bytes, used to restore previews.

The UI remembers only the result ID in the URL and refetches server data on refresh. Historical reads do not rerun models or create new analysis jobs. Replaceable Repository methods return deep copies and keep original/feedback stores separate. This slice retains the existing in-memory persistence: refresh/new service facade can recover history while the backend process lives; backend restart loses data. Cross-process durability and multi-process concurrency remain a PostgreSQL persistence task, not a completed production Stage 1D guarantee.

## Structured search

`KnowledgeRepository.search(StructuredSearchRequest)` is the replaceable query boundary. `StoredKnowledgeRepository` reads existing result/feature/review stores without seeding cases or calling models. A case is confirmed when every stored dimension's current review is accept/edit, semantics were successfully real, successful features exist, and all original semantic refs resolve. Rejecting any dimension immediately removes the case; later confirmation can restore it. Tags remain original model tags reviewed with the style dimension; text edits do not silently invent or replace tag values.

`POST /api/v1/search/structured`:

```json
{
  "tags": ["minimalist"],
  "numeric_filters": [
    {"feature_ref": "feature:composition_geometry#/negative_space_ratio", "op": "gte", "value": 0.5}
  ]
}
```

All tags and all numeric filters combine with AND. Operators are eq/gt/gte/lt/lte; equality uses the stored value exactly. Missing, failed, nonnumeric and Boolean feature values do not match; thresholds must be finite numbers. Unknown fields/operators are rejected. Empty filters list all confirmed real cases. Response items include asset/result/job IDs, filename, image URL, original tags, revision number and a short preview from current human-reviewed text. No semantic matching, vector indexes, rankings, collections or batches are implemented. Capabilities expose structured_search as available and semantic/hybrid as not_implemented.

Next retrieval step: implement PostgreSQL-backed Repository/KnowledgeRepository, persist original results, append-only feedback and confirmed case projection, and preserve these AND numeric/tag contract tests. Add restart-recovery tests before semantic/vector retrieval is introduced.
