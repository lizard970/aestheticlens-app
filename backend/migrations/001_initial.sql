CREATE TABLE IF NOT EXISTS assets (
    id uuid PRIMARY KEY,
    data jsonb NOT NULL,
    content bytea NOT NULL
);

CREATE TABLE IF NOT EXISTS analysis_jobs (
    id uuid PRIMARY KEY,
    asset_id uuid NOT NULL REFERENCES assets(id),
    created_at timestamptz NOT NULL,
    data jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS analysis_results (
    id uuid PRIMARY KEY,
    job_id uuid NOT NULL UNIQUE REFERENCES analysis_jobs(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    data jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS feature_results (
    result_id uuid NOT NULL REFERENCES analysis_results(id) ON DELETE CASCADE,
    position integer NOT NULL,
    data jsonb NOT NULL,
    PRIMARY KEY (result_id, position)
);

CREATE TABLE IF NOT EXISTS evidence_results (
    result_id uuid NOT NULL REFERENCES analysis_results(id) ON DELETE CASCADE,
    position integer NOT NULL,
    data jsonb NOT NULL,
    PRIMARY KEY (result_id, position)
);

CREATE TABLE IF NOT EXISTS feedback (
    id uuid PRIMARY KEY,
    result_id uuid NOT NULL REFERENCES analysis_results(id),
    revision integer NOT NULL CHECK (revision > 0),
    created_at timestamptz NOT NULL,
    data jsonb NOT NULL,
    UNIQUE (result_id, revision)
);

CREATE INDEX IF NOT EXISTS analysis_results_data_gin ON analysis_results USING gin (data);
CREATE INDEX IF NOT EXISTS feature_results_data_gin ON feature_results USING gin (data);
CREATE INDEX IF NOT EXISTS feedback_result_revision_desc ON feedback (result_id, revision DESC);
