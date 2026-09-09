CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS knowledge_case_embeddings (
    result_id uuid PRIMARY KEY REFERENCES analysis_results(id) ON DELETE CASCADE,
    revision integer NOT NULL CHECK (revision > 0),
    model text NOT NULL,
    source_text text NOT NULL,
    embedding vector(1536) NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS knowledge_case_embeddings_cosine_hnsw
    ON knowledge_case_embeddings USING hnsw (embedding vector_cosine_ops);
