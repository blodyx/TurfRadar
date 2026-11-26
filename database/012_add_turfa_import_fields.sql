ALTER TABLE user_taken_players
    ADD COLUMN imported_take_count INTEGER,
    ADD COLUMN imported_first_take_at TIMESTAMPTZ,
    ADD COLUMN imported_at TIMESTAMPTZ;

ALTER TABLE user_taken_players
    ADD CONSTRAINT user_taken_players_imported_take_count_check
    CHECK (imported_take_count IS NULL OR imported_take_count >= 0);
