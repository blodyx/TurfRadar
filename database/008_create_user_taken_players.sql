CREATE TABLE user_taken_players (
    user_id BIGINT NOT NULL
        REFERENCES users(id)
        ON DELETE CASCADE,

    opponent_turf_id BIGINT NOT NULL,
    opponent_name TEXT,

    first_observed_at TIMESTAMPTZ NOT NULL,
    last_observed_at TIMESTAMPTZ NOT NULL,

    observed_take_count INTEGER NOT NULL DEFAULT 1,

    PRIMARY KEY (
        user_id,
        opponent_turf_id
    )
);

CREATE INDEX user_taken_players_opponent_idx
    ON user_taken_players (opponent_turf_id);
