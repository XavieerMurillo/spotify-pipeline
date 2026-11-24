-- ============ FATO ============
CREATE TABLE IF NOT EXISTS fact_plays (
    played_at     TEXT NOT NULL,   -- fim da execução, UTC, sempre 'YYYY-MM-DDTHH:MM:SSZ' (sem ms)
    track_id      TEXT,            -- NULL possível (export sem URI)
    track_name    TEXT NOT NULL,   -- snapshot, sobrevive a track_id nulo
    artist_name   TEXT NOT NULL,   -- snapshot
    ms_played     INTEGER,         -- só o export tem
    reason_start  TEXT,            -- só o export
    reason_end    TEXT,            -- só o export
    shuffle       INTEGER,         -- só o export
    skipped       INTEGER,         -- só o export
    platform      TEXT,            -- só o export
    context_type  TEXT,            -- só a API (playlist/album/artist)
    context_uri   TEXT,            -- só a API
    source        TEXT NOT NULL,   -- 'api' | 'export'
    ingested_at   TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (played_at, track_name)
);

CREATE INDEX IF NOT EXISTS ix_plays_track ON fact_plays(track_id);
CREATE INDEX IF NOT EXISTS ix_plays_at    ON fact_plays(played_at);

-- ============ DIMENSÕES ============
CREATE TABLE IF NOT EXISTS dim_track (
    track_id      TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    album_id      TEXT,
    duration_ms   INTEGER,
    explicit      INTEGER,
    isrc          TEXT,
    track_number  INTEGER,
    disc_number   INTEGER,
    fetched_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS dim_artist (
    artist_id     TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    genres        TEXT,            -- JSON array
    fetched_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS dim_album (
    album_id               TEXT PRIMARY KEY,
    name                   TEXT NOT NULL,
    album_type             TEXT,
    release_date           TEXT,
    release_date_precision TEXT,   -- 'year' | 'month' | 'day'
    total_tracks           INTEGER,
    fetched_at             TEXT NOT NULL DEFAULT (datetime('now'))
);

-- track tem N artistas (feat.)
CREATE TABLE IF NOT EXISTS bridge_track_artist (
    track_id   TEXT NOT NULL,
    artist_id  TEXT NOT NULL,
    position   INTEGER NOT NULL,   -- 0 = principal
    PRIMARY KEY (track_id, artist_id)
);

-- fila de trabalho do enrich
CREATE TABLE IF NOT EXISTS enrich_queue (
    entity_type  TEXT NOT NULL,    -- 'track' | 'artist' | 'album'
    entity_id    TEXT NOT NULL,
    attempts     INTEGER NOT NULL DEFAULT 0,
    last_error   TEXT,
    PRIMARY KEY (entity_type, entity_id)
);
