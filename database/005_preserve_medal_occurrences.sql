DROP TABLE user_medals;

CREATE TABLE user_medals (
    id BIGSERIAL PRIMARY KEY,

    user_id BIGINT NOT NULL
        REFERENCES users(id)
        ON DELETE CASCADE,

    medal_id INTEGER NOT NULL,

    occurrence INTEGER NOT NULL
);

CREATE UNIQUE INDEX user_medals_occurrence_idx
    ON user_medals (user_id, medal_id, occurrence);

CREATE INDEX user_medals_medal_idx
    ON user_medals (medal_id);
