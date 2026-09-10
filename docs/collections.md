# Image collections

Uses the existing single-image analysis service unchanged. No new provider, dependencies,
frontend, video decoding, search eligibility changes, or automatic confirmation.

## Setup and API

Configure the existing `AESTHETICLENS_DATABASE_URL` in the environment, then run
`cd backend; python -m app.migrate` (includes `003_collections.sql`).
Without a database URL, the existing in-memory development repository remains available.

- `POST /api/v1/collections`: JSON `{"name":"Study","analysis_profile_id":"aesthetic-core-v1"}`.
- `POST /api/v1/collections/{collection_id}/items`: multipart repeated `files` fields,
  containing PNG/JPEG/WebP images and/or ZIP archives. Optional `timestamps_ms` is a
  JSON array such as `[0,null,200]`, matching the expanded image order.
- `POST /api/v1/collections/{collection_id}/process`: synchronous sequential processing.
- `GET /api/v1/collections/{collection_id}` and `/results`: collection, ordered items,
  persisted per-item job/result IDs, errors, coarse progress and aggregation snapshot.

Multipart order and ZIP entry order are preserved; positions are zero-based.
Non-image ZIP members are ignored. Archives are read without filesystem extraction;
unsafe paths and encrypted image entries are rejected. Limits are 100 images per
collection, 64 MiB total uploaded bytes per request, 64 MiB per expanded image and
256 MiB total expanded bytes. Existing image decoding limits still apply.

Each failed image is recorded and processing continues. A partial analysis retains
successful features. All failed items produce a failed collection; mixed/partial
results produce partial status. Progress is queued 0, running 20, terminal 100.
Concurrent upload/process calls for the same collection return `409 COLLECTION_BUSY`.
After restart, call `/process` to resume queued/interrupted items. Already saved
results are recovered without another model call. Completed and failed items are
not retried. There is no background worker or automatic restart scheduler.

## Aggregation boundaries

Failed items and failed features are excluded. Scalar top-level numeric feature
values yield count/min/max/mean/median/std/quartiles; nested arrays are not flattened.
Tag frequencies count once per image. Dimension summaries are extractive lists,
preferring current human revisions and excluding rejected/error-flagged dimensions.
Semantic failure contributes no semantic summary. Mock provenance remains explicit;
collection membership does not make a case searchable or confirmed.

Simple clustering uses shared stored scalar features, collection z-scores and
RMS-normalized Euclidean distance, average linkage with distance cutoff 1.0.
Representatives are cluster medoids. Outliers exceed Q3 + 1.5 IQR in distance from
the collection centroid; an empty outlier list is valid. With no shared features,
the response labels clustering `insufficient_features` and groups items together.
These descriptive heuristics are not aesthetic scores or learned semantic groups.
Aggregation is refreshed on `/process`, not automatically after later reviews.

## Verification

`cd backend; python -m pytest -q tests/test_collections.py`

Set `AESTHETICLENS_TEST_DATABASE_URL` to a dedicated PostgreSQL/pgvector test database
to include real restart persistence coverage. Tests do not call external models.
