-- ------------------------------------------------------------------
-- Migration 006: analysis ownership (Stage 18)
--
-- Ownership lineage (all by authenticated LabelLens subject):
--
--   ocr_runs (005) -> ocr_corrections (005) -> ingredient_observations
--   (005) -> ingredient_normalizations -> ingredient_candidates /
--   entity_matches -> verification_decisions -> reviews
--
-- Table classification (see STAGE_18 and DATABASE_SCHEMA §77d):
--   user-owned (this migration): ingredient_normalizations,
--     ingredient_candidates, entity_matches, verification_decisions,
--     reviews. New writes always carry the data owner's subject;
--     legacy NULL rows keep prior readability.
--   shared canonical (never owned): chemical_entities,
--     ingredient_aliases, sources, domains, roles.
--   shared by content (never owned, never forked): claims,
--     claim_sources, verification_events. Claim identity is
--     deterministic chemistry content shared across observers.
--   global audit (never owned): review_events. Reachable only via
--     an owned-or-reviewer review read at the service layer.
--
-- Service role bypasses RLS by design (backend-only), as in
-- 003/004/005. Authenticated writes stay denied everywhere.
-- ------------------------------------------------------------------
ALTER TABLE ingredient_normalizations
    ADD COLUMN IF NOT EXISTS owner_subject TEXT;
ALTER TABLE ingredient_candidates
    ADD COLUMN IF NOT EXISTS owner_subject TEXT;
ALTER TABLE entity_matches
    ADD COLUMN IF NOT EXISTS owner_subject TEXT;
ALTER TABLE verification_decisions
    ADD COLUMN IF NOT EXISTS owner_subject TEXT;
ALTER TABLE reviews
    ADD COLUMN IF NOT EXISTS owner_subject TEXT;

-- Legacy rows predate ownership and keep prior readability
-- (NULL matches no subject, so nothing new becomes visible).
-- No backfill invents historical ownership.

ALTER TABLE ingredient_normalizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingredient_candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE entity_matches ENABLE ROW LEVEL SECURITY;
ALTER TABLE verification_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE reviews ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS ingredient_normalizations_owner_read
    ON ingredient_normalizations;
DROP POLICY IF EXISTS ingredient_candidates_owner_read
    ON ingredient_candidates;
DROP POLICY IF EXISTS entity_matches_owner_read ON entity_matches;
DROP POLICY IF EXISTS verification_decisions_owner_read
    ON verification_decisions;
DROP POLICY IF EXISTS reviews_owner_read ON reviews;
-- Retire the permissive 003 audit policies on the two tables that
-- become owner-scoped. Permissive policies combine with OR, so
-- leaving these would silently preserve global readability.
-- (claims, claim_sources, verification_events, and review_events
-- keep their global audit policies by design: shared chemistry
-- truth and audit without private content.)
DROP POLICY IF EXISTS audit_read_decisions
    ON verification_decisions;
DROP POLICY IF EXISTS audit_read_reviews ON reviews;

CREATE POLICY ingredient_normalizations_owner_read
    ON ingredient_normalizations FOR SELECT TO authenticated
    USING (
        owner_subject IS NULL
        OR owner_subject = current_setting('app.current_subject', true)
    );
CREATE POLICY ingredient_candidates_owner_read
    ON ingredient_candidates FOR SELECT TO authenticated
    USING (
        owner_subject IS NULL
        OR owner_subject = current_setting('app.current_subject', true)
    );
CREATE POLICY entity_matches_owner_read
    ON entity_matches FOR SELECT TO authenticated
    USING (
        owner_subject IS NULL
        OR owner_subject = current_setting('app.current_subject', true)
    );
CREATE POLICY verification_decisions_owner_read
    ON verification_decisions FOR SELECT TO authenticated
    USING (
        owner_subject IS NULL
        OR owner_subject = current_setting('app.current_subject', true)
    );
-- Reviews: owners read their own (plus legacy NULL rows).
-- Reviewers read everything, but only through the API: the
-- service role bypasses RLS and the service layer checks the
-- reviewer role instead of the owner. Direct database access as
-- the authenticated role stays owner-scoped by this policy.
CREATE POLICY reviews_owner_read
    ON reviews FOR SELECT TO authenticated
    USING (
        owner_subject IS NULL
        OR owner_subject = current_setting('app.current_subject', true)
    );
-- No INSERT/UPDATE/DELETE policies anywhere here: authenticated
-- writes stay denied (default deny); all writes go through the
-- service role.

-- Table privileges: 003 revoked everything from authenticated on
-- these tables, so each policy needs its SELECT grant alongside.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated')
    THEN
        EXECUTE 'GRANT SELECT ON ingredient_normalizations TO authenticated';
        EXECUTE 'GRANT SELECT ON ingredient_candidates TO authenticated';
        EXECUTE 'GRANT SELECT ON entity_matches TO authenticated';
        EXECUTE 'GRANT SELECT ON verification_decisions TO authenticated';
        EXECUTE 'GRANT SELECT ON reviews TO authenticated';
    END IF;
END $$;
