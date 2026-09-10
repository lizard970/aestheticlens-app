CREATE TABLE IF NOT EXISTS asset_collections (
    id uuid PRIMARY KEY,
    data jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS collection_items (
    id uuid PRIMARY KEY,
    collection_id uuid NOT NULL REFERENCES asset_collections(id),
    asset_id uuid NOT NULL REFERENCES assets(id),
    position integer NOT NULL CHECK (position >= 0),
    data jsonb NOT NULL,
    UNIQUE (collection_id, position)
);
