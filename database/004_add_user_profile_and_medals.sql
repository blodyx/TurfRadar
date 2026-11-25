ALTER TABLE users
    ADD COLUMN country TEXT,
    ADD COLUMN region_id BIGINT,
    ADD COLUMN region_name TEXT,
    ADD COLUMN unique_zones_taken INTEGER,
    ADD COLUMN total_takes INTEGER,
    ADD COLUMN rank INTEGER,
    ADD COLUMN total_points BIGINT,
    ADD COLUMN profile_updated_at TIMESTAMPTZ;

CREATE TABLE user_medals (
    user_id BIGINT NOT NULL
        REFERENCES users(id)
        ON DELETE CASCADE,

    medal_id INTEGER NOT NULL,

    PRIMARY KEY (user_id, medal_id)
);

CREATE INDEX user_medals_medal_idx
    ON user_medals (medal_id);
