CREATE TABLE turfa_taken_players (
    id BIGSERIAL PRIMARY KEY,

    user_id BIGINT NOT NULL
        REFERENCES users(id)
        ON DELETE CASCADE,

    opponent_name TEXT NOT NULL,
    opponent_name_normalized TEXT NOT NULL,

    opponent_turf_id BIGINT,

    take_count INTEGER NOT NULL
        CHECK (take_count > 0),

    first_take_at TIMESTAMPTZ,

    imported_at TIMESTAMPTZ NOT NULL
        DEFAULT NOW(),

    UNIQUE (
        user_id,
        opponent_name_normalized
    )
);

CREATE INDEX turfa_taken_players_user_idx
    ON turfa_taken_players (user_id);

CREATE INDEX turfa_taken_players_turf_id_idx
    ON turfa_taken_players (
        user_id,
        opponent_turf_id
    );

CREATE INDEX turfa_taken_players_name_idx
    ON turfa_taken_players (
        user_id,
        opponent_name_normalized
    );
