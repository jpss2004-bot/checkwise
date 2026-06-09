-- Post-deploy verification for the checklist hardening migrations
-- (0034 indexes, 0035 slot-uniqueness, 0036 status CHECK).
-- Run against the prod Neon branch (DIRECT endpoint). 2026-06-09.
--
-- Expectation after a clean `alembic upgrade head`:
--   * alembic_version = 0036_status_check_constraints
--   * the 4 submissions + 2 documents indexes from 0034 exist
--   * ux_submissions_active_slot exists AND is valid (indisvalid = true)
--   * ck_submissions_status / ck_documents_status exist
--   * no slot currently holds >1 active-genesis row (the invariant)

-- 1. Migration head ----------------------------------------------------------
SELECT version_num FROM alembic_version;   -- expect: 0036_status_check_constraints

-- 2. Indexes from 0034 + the unique index from 0035, with validity ----------
SELECT
    i.relname              AS index_name,
    idx.indisvalid         AS is_valid,      -- MUST be true for the unique one
    idx.indisunique        AS is_unique,
    pg_get_indexdef(idx.indexrelid) AS definition
FROM pg_index idx
JOIN pg_class i ON i.oid = idx.indexrelid
JOIN pg_class t ON t.oid = idx.indrelid
WHERE t.relname IN ('submissions', 'documents', 'document_status_history', 'audit_log')
  AND i.relname IN (
        'ix_submissions_client_vendor', 'ix_submissions_client_status',
        'ix_submissions_period_id', 'ix_submissions_requirement_id',
        'ix_documents_submission_id', 'ix_documents_status',
        'ix_doc_status_history_document', 'ix_doc_status_history_submission',
        'ix_audit_log_entity', 'ix_audit_log_actor',
        'ux_submissions_active_slot'
  )
ORDER BY t.relname, i.relname;
-- ⚠ If ux_submissions_active_slot shows is_valid = false, the CONCURRENTLY
--   build aborted on a straggler dup: re-run `alembic downgrade -1` then
--   `alembic upgrade head` (0035 drops the invalid index first), after the
--   duplicate check in step 5 returns zero rows.

-- 3. CHECK constraints from 0036 --------------------------------------------
SELECT conname, convalidated,                -- convalidated=false is expected (NOT VALID)
       pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conname IN ('ck_submissions_status', 'ck_documents_status');

-- 4. (Optional) validate the CHECK once stragglers are confirmed clean -------
--   First confirm zero out-of-enum rows exist, then VALIDATE to enforce on
--   the whole table (cheap, takes a SHARE UPDATE EXCLUSIVE lock briefly):
-- SELECT status, count(*) FROM submissions GROUP BY status;   -- eyeball the enum
-- ALTER TABLE submissions VALIDATE CONSTRAINT ck_submissions_status;
-- ALTER TABLE documents   VALIDATE CONSTRAINT ck_documents_status;

-- 5. Invariant spot-check: no slot has >1 active-genesis submission ----------
SELECT client_id, vendor_id, requirement_code, COALESCE(period_key, '') AS pk,
       count(*) AS active_genesis
FROM submissions
WHERE supersedes_submission_id IS NULL
  AND requirement_code IS NOT NULL
GROUP BY client_id, vendor_id, requirement_code, COALESCE(period_key, '')
HAVING count(*) > 1;
-- Expect: 0 rows. (Non-zero would mean the de-dup backfill didn't run or new
-- dups slipped in before auto-supersede deployed — which can't happen now,
-- so this should stay empty.)
