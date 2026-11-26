CREATE TABLE radar_player_state (
    user_id BIGINT NOT NULL
        REFERENCES users(id)
        ON DELETE CASCADE,

    opponent_turf_id BIGINT NOT NULL,

    opponent_name TEXT,

    currently_visible BOOLEAN NOT NULL
        DEFAULT FALSE,

    first_seen_at TIMESTAMPTZ NOT NULL
        DEFAULT NOW(),

    last_seen_at TIMESTAMPTZ NOT NULL
        DEFAULT NOW(),

    notified_at TIMESTAMPTZ,

    PRIMARY KEY (
        user_id,
        opponent_turf_id
    )
);

CREATE INDEX radar_player_state_visible_idx
    ON radar_player_state (
        user_id,
        currently_visible
    );
