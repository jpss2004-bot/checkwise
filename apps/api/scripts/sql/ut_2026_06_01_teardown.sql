-- ============================================================================
-- ut_2026_06_01_teardown.sql
--
-- OFF-SWITCH for the 2026-06-01 user-testing synthetic tenant.
--
-- Removes every row created by ut_2026_06_01_seed.sql and the prep.py
-- companion script. Scoped strictly by the six tag conventions:
--
--   1. clients.name                contains  'User Testing'  (CLIENT_NAME)
--   2. clients.rfc                 =         'CUT260601AA1'
--   3. users.email                 LIKE      '%@checkwise.local'
--   4. provider_workspaces.id      LIKE      'ut-20260601-%'
--   5. provider_workspaces.access_token LIKE 'ut-local-token-%'
--   6. documents.storage_key       LIKE      'user-testing/2026-06-01/%'
--      submissions.comments        LIKE      '%user_testing_2026_06_01%'
--      periods.code                LIKE      'user_testing_2026_06_01-%'
--      audit_log.action            =         'user_testing.scenario_seeded'
--
-- Idempotent — re-running on already-empty data is a no-op.
-- Single transaction — rolls back cleanly on any error.
--
-- Run:  psql "$DATABASE_URL" -f scripts/sql/ut_2026_06_01_teardown.sql
--
-- NOTE: this does NOT delete the R2/S3 objects under
--       user-testing/2026-06-01/ . That cleanup is in the prep.py
--       script with the --teardown-storage flag.
-- ============================================================================

\set ON_ERROR_STOP on

BEGIN;

-- Pin the synthetic client id so every subsequent DELETE is bounded by it.
-- The CTE form keeps this readable; we use a temp table so multiple
-- statements can reference the same row set without re-running the SELECT.
CREATE TEMP TABLE _ut_client ON COMMIT DROP AS
SELECT id
FROM clients
WHERE rfc = 'CUT260601AA1'
   OR name LIKE '%User Testing%';

CREATE TEMP TABLE _ut_vendor ON COMMIT DROP AS
SELECT v.id
FROM vendors v
WHERE v.client_id IN (SELECT id FROM _ut_client)
   OR v.rfc IN ('SAS260601AA1', 'SBS260601BB2', 'SCS260601CC3');

CREATE TEMP TABLE _ut_workspace ON COMMIT DROP AS
SELECT w.id
FROM provider_workspaces w
WHERE w.id LIKE 'ut-20260601-%'
   OR w.access_token LIKE 'ut-local-token-%'
   OR w.vendor_id IN (SELECT id FROM _ut_vendor);

CREATE TEMP TABLE _ut_user ON COMMIT DROP AS
SELECT id
FROM users
WHERE email LIKE '%@checkwise.local';

CREATE TEMP TABLE _ut_org ON COMMIT DROP AS
SELECT id
FROM organizations
WHERE name LIKE '%User Testing%'
   OR client_id IN (SELECT id FROM _ut_client);

CREATE TEMP TABLE _ut_submission ON COMMIT DROP AS
SELECT s.id
FROM submissions s
WHERE s.vendor_id IN (SELECT id FROM _ut_vendor)
   OR s.comments LIKE '%user_testing_2026_06_01%';

CREATE TEMP TABLE _ut_document ON COMMIT DROP AS
SELECT d.id
FROM documents d
WHERE d.submission_id IN (SELECT id FROM _ut_submission)
   OR d.storage_key LIKE 'user-testing/2026-06-01/%';

CREATE TEMP TABLE _ut_report ON COMMIT DROP AS
SELECT r.id
FROM reports r
WHERE r.organization_id IN (SELECT id FROM _ut_org);

CREATE TEMP TABLE _ut_period ON COMMIT DROP AS
SELECT id
FROM periods
WHERE code LIKE 'user_testing_2026_06_01-%';

-- Surface row counts BEFORE deletion so an operator running this
-- interactively can sanity-check the blast radius.
\echo '--- teardown candidates ---'
SELECT 'clients'             AS table, COUNT(*) AS rows FROM _ut_client
UNION ALL SELECT 'vendors',            COUNT(*) FROM _ut_vendor
UNION ALL SELECT 'workspaces',         COUNT(*) FROM _ut_workspace
UNION ALL SELECT 'users',              COUNT(*) FROM _ut_user
UNION ALL SELECT 'organizations',      COUNT(*) FROM _ut_org
UNION ALL SELECT 'submissions',        COUNT(*) FROM _ut_submission
UNION ALL SELECT 'documents',          COUNT(*) FROM _ut_document
UNION ALL SELECT 'reports',            COUNT(*) FROM _ut_report
UNION ALL SELECT 'periods',            COUNT(*) FROM _ut_period;

-- ============================================================================
-- DELETIONS (leaves → roots)
-- ============================================================================

-- Document graph (leaves)
DELETE FROM validation_events       WHERE document_id IN (SELECT id FROM _ut_document)
                                       OR submission_id IN (SELECT id FROM _ut_submission);
DELETE FROM validations             WHERE document_id IN (SELECT id FROM _ut_document)
                                       OR submission_id IN (SELECT id FROM _ut_submission);
DELETE FROM document_status_history WHERE document_id IN (SELECT id FROM _ut_document)
                                       OR submission_id IN (SELECT id FROM _ut_submission);
DELETE FROM document_inspections    WHERE document_id IN (SELECT id FROM _ut_document);
DELETE FROM documents               WHERE id IN (SELECT id FROM _ut_document);

-- Submissions and their tagged-only siblings (e.g. submissions without docs)
DELETE FROM submissions             WHERE id IN (SELECT id FROM _ut_submission);

-- Report graph (in case any reports were generated against the synthetic org)
DELETE FROM report_conversations    WHERE report_id IN (SELECT id FROM _ut_report);
DELETE FROM report_exports          WHERE report_id IN (SELECT id FROM _ut_report);
DELETE FROM report_shares           WHERE report_id IN (SELECT id FROM _ut_report);
DELETE FROM report_versions         WHERE report_id IN (SELECT id FROM _ut_report);
DELETE FROM reports                 WHERE id IN (SELECT id FROM _ut_report);

-- Workspace-attached side tables
DELETE FROM wise_events             WHERE workspace_id IN (SELECT id FROM _ut_workspace);
DELETE FROM renewal_reminders       WHERE workspace_id IN (SELECT id FROM _ut_workspace);
DELETE FROM provider_notifications  WHERE workspace_id IN (SELECT id FROM _ut_workspace);

-- Client-attached notifications and snapshots
DELETE FROM client_notifications    WHERE client_id IN (SELECT id FROM _ut_client);
DELETE FROM compliance_snapshots    WHERE organization_id IN (SELECT id FROM _ut_org);

-- Workspaces, then vendors
DELETE FROM provider_workspaces     WHERE id IN (SELECT id FROM _ut_workspace);
DELETE FROM vendors                 WHERE id IN (SELECT id FROM _ut_vendor);

-- Memberships and orgs
DELETE FROM memberships             WHERE user_id IN (SELECT id FROM _ut_user)
                                       OR organization_id IN (SELECT id FROM _ut_org);
DELETE FROM organizations           WHERE id IN (SELECT id FROM _ut_org);

-- Synthetic users (cascading deletes on password_history, user_notification_preferences,
-- phone_verifications, password_reset_tokens are handled by FK CASCADE)
DELETE FROM users                   WHERE id IN (SELECT id FROM _ut_user);

-- Synthetic client
DELETE FROM clients                 WHERE id IN (SELECT id FROM _ut_client);

-- Synthetic periods (DO NOT touch shared catalog periods — these are tag-prefixed)
DELETE FROM periods                 WHERE id IN (SELECT id FROM _ut_period);

-- Audit trail for the scenario itself (keep ALL other audit history intact)
DELETE FROM audit_log
WHERE action = 'user_testing.scenario_seeded'
   OR (entity_type = 'client' AND entity_id IN (SELECT id FROM _ut_client));

-- ============================================================================
-- VERIFICATION — must read all zeros for a clean teardown.
-- ============================================================================
\echo '--- residual rows (should all be 0) ---'
SELECT 'clients'            AS table, COUNT(*) AS residual FROM clients            WHERE rfc = 'CUT260601AA1' OR name LIKE '%User Testing%'
UNION ALL SELECT 'vendors',           COUNT(*) FROM vendors            WHERE rfc IN ('SAS260601AA1', 'SBS260601BB2', 'SCS260601CC3')
UNION ALL SELECT 'workspaces',        COUNT(*) FROM provider_workspaces WHERE id LIKE 'ut-20260601-%' OR access_token LIKE 'ut-local-token-%'
UNION ALL SELECT 'users',             COUNT(*) FROM users              WHERE email LIKE '%@checkwise.local'
UNION ALL SELECT 'organizations',     COUNT(*) FROM organizations      WHERE name LIKE '%User Testing%'
UNION ALL SELECT 'submissions',       COUNT(*) FROM submissions        WHERE comments LIKE '%user_testing_2026_06_01%'
UNION ALL SELECT 'documents',         COUNT(*) FROM documents          WHERE storage_key LIKE 'user-testing/2026-06-01/%'
UNION ALL SELECT 'periods',           COUNT(*) FROM periods            WHERE code LIKE 'user_testing_2026_06_01-%'
UNION ALL SELECT 'audit_log',         COUNT(*) FROM audit_log          WHERE action = 'user_testing.scenario_seeded';

COMMIT;

\echo 'teardown complete.'
