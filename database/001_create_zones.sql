CREATE TABLE zones (
    id BIGINT PRIMARY KEY,
    name TEXT NOT NULL,

    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    location GEOGRAPHY(POINT, 4326) NOT NULL,

    current_owner_id BIGINT,
    current_owner_name TEXT,

    region_id BIGINT,
    region_name TEXT,

    area_id BIGINT,
    area_name TEXT,
    country TEXT,

    zone_type_id INTEGER,
    zone_type_name TEXT,

    points_per_hour INTEGER,
    takeover_points INTEGER,
    total_takeovers INTEGER,

    date_created TIMESTAMPTZ,
    date_last_taken TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX zones_location_idx
    ON zones
    USING GIST (location);

CREATE INDEX zones_current_owner_idx
    ON zones (current_owner_id);

CREATE INDEX zones_region_idx
    ON zones (region_id);
