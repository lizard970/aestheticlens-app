CREATE TABLE IF NOT EXISTS evaluation_cases (
    id uuid PRIMARY KEY,
    asset_id uuid NOT NULL REFERENCES assets(id),
    data jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS evaluation_runs (
    id uuid PRIMARY KEY,
    case_id uuid NOT NULL REFERENCES evaluation_cases(id),
    data jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS evaluation_feedback (
    id uuid PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES evaluation_runs(id),
    data jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS evaluation_feedback_run_idx ON evaluation_feedback(run_id);
