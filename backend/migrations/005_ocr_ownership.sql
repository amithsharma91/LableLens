-- ------------------------------------------------------------------
-- Migration 005: per-user ownership (Stage 17)
--
-- ocr_runs.owner_subject and ocr_corrections.owner_subject are the
-- authenticated LabelLens subject that owns the run (JWT sub or
-- static-token subject -- never a token, never a provider account).
-- ingredient_observations.owner_subject is NULL for pre-ownership
-- rows (direct observations, regression fixtures) and set for every
-- observation the API creates from Stage 17 on.
--
-- Enforcement is two-layer: the service compares row owners against
-- the authenticated principal (foreign rows answer 404 so resources
-- cannot be enumerated), and these RLS policies isolate direct
-- database access as the authenticated role. The service role
-- bypasses RLS by design (backend-only), exactly as in 003/004.
-- Per-user scoping of claims/reviews/audit events is still open:
-- those rows carry no owner yet.
-- ------------------------------------------------------------------
ALTER TABLE ocr_runs
    ADD COLUMN IF NOT EXISTS owner_subject TEXT;
ALTER TABLE ocr_corrections
    ADD COLUMN IF NOT EXISTS owner_subject TEXT;
ALTER TABLE ingredient_observations
    ADD COLUMN IF NOT EXISTS owner_subject TEXT;

-- Backfill: pre-ownership OCR rows belong to no one and stay
-- unreadable to authenticated roles (owner IS NULL matches no
-- subject, by construction).
UPDATE ocr_runs SET owner_subject = '' WHERE owner_subject IS NULL;
UPDATE ocr_corrections SET owner_subject = '' WHERE owner_subject IS NULL;

ALTER TABLE ocr_runs
    ALTER COLUMN owner_subject SET NOT NULL;
ALTER TABLE ocr_corrections
    ALTER COLUMN owner_subject SET NOT NULL;

-- Replace the permissive 004 audit policies with owner-scoped ones.
DROP POLICY IF EXISTS audit_read_ocr_runs ON ocr_runs;
DROP POLICY IF EXISTS audit_read_ocr_corrections ON ocr_corrections;
DROP POLICY IF EXISTS ocr_runs_owner_read ON ocr_runs;
DROP POLICY IF EXISTS ocr_corrections_owner_read ON ocr_corrections;
DROP POLICY IF EXISTS ingredient_observations_owner_read
    ON ingredient_observations;

CREATE POLICY ocr_runs_owner_read ON ocr_runs
    FOR SELECT TO authenticated
    USING (owner_subject = current_setting('app.current_subject', true));
CREATE POLICY ocr_corrections_owner_read ON ocr_corrections
    FOR SELECT TO authenticated
    USING (owner_subject = current_setting('app.current_subject', true));
-- No INSERT/UPDATE/DELETE policies: authenticated writes stay
-- denied (default deny); all writes go through the service role.

-- Observations: legacy NULL-owner rows keep the previous
-- authenticated readability; owned rows are isolated per subject.
-- (No prior SELECT policy existed on this table; authenticated
-- direct reads were fully denied before this migration.)
CREATE POLICY ingredient_observations_owner_read
    ON ingredient_observations FOR SELECT TO authenticated
    USING (
        owner_subject IS NULL
        OR owner_subject = current_setting('app.current_subject', true)
    );

-- Table privileges: 003 revoked everything from authenticated on
-- this table, so the policy alone is not enough -- the SELECT
-- grant below re-opens exactly what the policy allows. The ocr_*
-- grants already live in 004.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated')
    THEN
        EXECUTE 'GRANT SELECT ON ingredient_observations TO authenticated';
    END IF;
END $$;