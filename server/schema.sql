-- One row per video/short, shared across all users
CREATE TABLE IF NOT EXISTS items (
    item_id        TEXT PRIMARY KEY,
    platform       TEXT NOT NULL,
    media_type     TEXT NOT NULL,
    title          TEXT,
    channel        TEXT,
    channel_handle TEXT,
    duration       TEXT,
    is_ad          BOOLEAN NOT NULL DEFAULT FALSE,
    first_seen_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- One row per impression. The fact table.
CREATE TABLE IF NOT EXISTS impressions (
    id          BIGSERIAL PRIMARY KEY,
    user_token  TEXT NOT NULL,
    item_id     TEXT NOT NULL REFERENCES items(item_id),
    position    INT,
    entered_at  TIMESTAMPTZ NOT NULL,
    dwell_ms    INT NOT NULL,
    source      TEXT NOT NULL,
    evidence    TEXT NOT NULL,
    phase       TEXT,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- a retry can never double count
    UNIQUE (user_token, item_id, entered_at)
);

CREATE INDEX IF NOT EXISTS impressions_user_time ON impressions (user_token, entered_at);

CREATE TABLE IF NOT EXISTS item_labels (
    item_id       TEXT PRIMARY KEY REFERENCES items(item_id),
    topic         TEXT NOT NULL,
    tone          TEXT NOT NULL,
    confidence    REAL,
    model_version TEXT NOT NULL,
    labeled_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);