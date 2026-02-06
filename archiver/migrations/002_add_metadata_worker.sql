-- Add metadata worker fields to scanner_state

ALTER TABLE scanner_state ADD COLUMN IF NOT EXISTS metadata_enabled BOOLEAN DEFAULT TRUE;
ALTER TABLE scanner_state ADD COLUMN IF NOT EXISTS threads_enabled BOOLEAN DEFAULT TRUE;
ALTER TABLE scanner_state ADD COLUMN IF NOT EXISTS comments_enabled BOOLEAN DEFAULT FALSE;

ALTER TABLE scanner_state ADD COLUMN IF NOT EXISTS metadata_weight FLOAT DEFAULT 0.2;
ALTER TABLE scanner_state ADD COLUMN IF NOT EXISTS threads_weight FLOAT DEFAULT 0.6;
ALTER TABLE scanner_state ADD COLUMN IF NOT EXISTS comments_weight FLOAT DEFAULT 0.2;

ALTER TABLE scanner_state ADD COLUMN IF NOT EXISTS metadata_subs_processed INTEGER DEFAULT 0;
ALTER TABLE scanner_state ADD COLUMN IF NOT EXISTS metadata_subs_discovered INTEGER DEFAULT 0;
ALTER TABLE scanner_state ADD COLUMN IF NOT EXISTS last_metadata_activity BIGINT;
ALTER TABLE scanner_state ADD COLUMN IF NOT EXISTS csv_remaining INTEGER DEFAULT 0;
