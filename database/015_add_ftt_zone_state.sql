ALTER TABLE zones
    ADD COLUMN date_created TIMESTAMPTZ,
    ADD COLUMN total_takeovers INTEGER,
    ADD COLUMN is_ftt_candidate BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX zones_ftt_candidate_idx
    ON zones (is_ftt_candidate)
    WHERE is_ftt_candidate = TRUE;
