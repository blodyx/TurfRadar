CREATE TABLE user_taken_zones (
    user_id BIGINT NOT NULL
        REFERENCES users(id)
        ON DELETE CASCADE,

    zone_id BIGINT NOT NULL
        REFERENCES zones(id)
        ON DELETE CASCADE,

    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (user_id, zone_id)
);

CREATE INDEX user_taken_zones_zone_idx
    ON user_taken_zones (zone_id);
