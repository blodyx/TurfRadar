CREATE TABLE auth_challenges (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL
        REFERENCES users(id)
        ON DELETE CASCADE,
    challenge_hash TEXT NOT NULL UNIQUE,
    verified_at TIMESTAMPTZ,
    claimed_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX auth_challenges_user_idx
    ON auth_challenges (user_id);

CREATE INDEX auth_challenges_expires_idx
    ON auth_challenges (expires_at);
