# Stage 1D hybrid search

`POST /api/v1/search/hybrid` combines the existing structured eligibility/filter rules with the
existing stored case embeddings. Tags and numeric filters are hard AND constraints. When `query`
is present, cosine similarity ranks only the result IDs that passed those constraints. With no
query, the endpoint returns structured matches with `similarity: null` and does not call the
embedding provider.

Hybrid numeric filters use a public `field` key. A full `feature:<extractor>#/pointer` remains
accepted, plain leaf names resolve only when unambiguous, and `shadow_occupancy` explicitly maps to
`feature:tonal_occupancy#/shadow_share`. Each result echoes the matched tag and numeric constraints
alongside IDs, similarity, tags, filename/preview URL, revision, and a short interpretation preview.

The structured and semantic endpoints are unchanged. Eligibility still excludes unconfirmed,
rejected, Mock, failed-semantic, failed-feature, and invalid-evidence cases. Hybrid search adds no
RAG, reranker, collections, or UI.
