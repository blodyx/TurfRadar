CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,

    turf_user_id BIGINT UNIQUE NOT NULL,
    turf_name TEXT NOT NULL,

    radius_m INTEGER NOT NULL DEFAULT 2000,

    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    location GEOGRAPHY(POINT, 4326),
    position_updated_at TIMESTAMPTZ,

    active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX users_location_idx
    ON users
    USING GIST (location);
