CREATE TABLE radar_ftt_state (
    user_id BIGINT NOT NULL
        REFERENCES users(id)
        ON DELETE CASCADE,

    zone_id BIGINT NOT NULL
        REFERENCES zones(id)
        ON DELETE CASCADE,

    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notified_at TIMESTAMPTZ,

    PRIMARY KEY (user_id, zone_id)
);

CREATE INDEX radar_ftt_state_user_idx
    ON radar_ftt_state (user_id);
