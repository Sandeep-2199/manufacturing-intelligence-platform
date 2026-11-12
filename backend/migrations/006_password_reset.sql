ALTER TABLE team_users
    ADD COLUMN reset_token_hash varchar(64) UNIQUE,
    ADD COLUMN reset_expires_at timestamptz;
