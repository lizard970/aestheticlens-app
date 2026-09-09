# Stage 1D semantic search

`EmbeddingAdapter` isolates the external provider. The first configured adapter calls OpenAI's
`POST /v1/embeddings` endpoint with `text-embedding-3-small` by default and a fixed 1536-dimensional
float response. Provider, API base URL, model, key, and timeout come only from environment variables.

`knowledge_case_embeddings` stores at most one pgvector row per analysis result. A row exists only
while the existing structured-search eligibility rules pass: real successful semantics, successful
features, resolvable evidence, and every current dimension accepted or edited. Each feedback write
re-evaluates the full current revision, upserting an eligible row or deleting an ineligible row.
`python -m app.reindex_embeddings` applies the same rule to cases confirmed before this migration.
If the external provider or vector index is temporarily unavailable, feedback still persists and the
failed refresh is logged; rerunning the reindex command repairs any missing or stale row.

Embedding text contains only the original summary, style tags, and current reviewed dimension
interpretations. Edited human interpretations replace their raw model counterparts. Feature JSON,
asset bytes, evidence values, feedback comments, and error metadata are not embedded.

`POST /api/v1/search/semantic` embeds the query and performs cosine nearest-neighbor search in
PostgreSQL. It returns identifiers, similarity, tags, filename/preview URL, revision, and one short
interpretation preview. Structured search is unchanged; hybrid search, RAG, collections, and
reranking remain unavailable.
