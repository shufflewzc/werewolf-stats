-- The canonical schema creates the new runtime tables for fresh installations.
-- This numbered migration records and verifies the v6 production transition.
UPDATE players
SET profile_status = 'auto_created',
    created_source = CASE
        WHEN created_source = '' OR created_source = 'manual' THEN 'match_entry'
        ELSE created_source
    END
WHERE notes LIKE '%自动创建%'
  AND profile_status = 'verified';

INSERT INTO data_revisions (revision_key, revision, updated_at_epoch)
VALUES ('repository', 1, EXTRACT(EPOCH FROM NOW())::BIGINT)
ON CONFLICT (revision_key) DO NOTHING;
