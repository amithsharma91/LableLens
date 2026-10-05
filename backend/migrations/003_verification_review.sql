-- 003_verification_review.sql — Stage-10 persistence boundary
--
-- Adds the verification/claim/evidence/review tables required by
-- DATABASE_SCHEMA.md (§§11-14, 25-27) plus the three gate-specified
-- records the schema does not yet define (verification_decisions,
-- reviews, review_events). Additive only: no existing table is
-- altered except sources (UNIQUE name for idempotent seeding) and
-- no history is rewritten.
--
-- Deferred FKs (documented): product_id, product_label_id,
-- entity_role_id (claims), scan_id and ocr_run_id
-- (ingredient_observations) reference product/scan/role tables that
-- land in a later phase. They are stored as plain UUIDs here; FK
-- constraints activate with those tables. Passing a random UUID is
-- allowed at this layer; product-bound writes belong to later
-- stages with their own validation.
--
-- RLS posture: enabled on every new table. Reads on audit tables
-- are open to the authenticated role; ALL writes stay with the
-- service role (RLS bypass by design, backend-only). Event tables
-- additionally carry a database trigger rejecting UPDATE/DELETE.
-- This is a conservative default, NOT a tested production posture.

-- ------------------------------------------------------------------
-- Repair: 002_seed_data sources used non-hex UUIDs (g/h/i prefixes)
-- so its source INSERT inserted zero rows. Re-seed idempotently.
-- ------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'sources_name_unique'
    ) THEN
        ALTER TABLE sources
            ADD CONSTRAINT sources_name_unique UNIQUE (name);
    END IF;
END $$;

INSERT INTO sources (id, name, source_type, authority_level, status)
SELECT v.id::UUID, v.name, v.source_type, v.authority_level, v.status
FROM (VALUES
    ('a1111111-1111-1111-1111-111111111111', 'PUBCHEM', 'scientific_database', 'high', 'approved'),
    ('b2222222-2222-2222-2222-222222222222', 'CHEBI', 'scientific_database', 'high', 'approved'),
    ('c3333333-3333-3333-3333-333333333333', 'NIST_WEBBOOK', 'scientific_database', 'high', 'conditional'),
    ('d4444444-4444-4444-4444-444444444444', 'RDKIT', 'software_methodology', 'high', 'approved'),
    ('e5555555-5555-5555-5555-555555555555', 'FSSAI_FOOD_REGS', 'regulatory', 'high', 'approved'),
    ('f6666666-6666-6666-6666-666666666666', 'CODEX_GSFA', 'regulatory', 'high', 'approved'),
    ('77777777-7777-7777-7777-777777777777', 'EU_FOOD_ADDITIVES', 'regulatory', 'high', 'approved'),
    ('88888888-8888-8888-8888-888888888888', 'FDA_FOOD_ADDITIVES', 'regulatory', 'high', 'approved'),
    ('99999999-9999-9999-9999-999999999999', 'EU_COSING', 'informational', 'high', 'approved')
) AS v(id, name, source_type, authority_level, status)
WHERE NOT EXISTS (SELECT 1 FROM sources s WHERE s.name = v.name);

-- ------------------------------------------------------------------
-- Observation / normalization / candidate / match chain (§§11-14)
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ingredient_observations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    scan_id UUID NOT NULL,
    sequence_number INTEGER NOT NULL,
    raw_text TEXT NOT NULL,
    display_text TEXT NULL,
    source_type TEXT NOT NULL,
    ocr_run_id UUID NULL,
    ocr_confidence NUMERIC NULL,
    user_corrected BOOLEAN NOT NULL DEFAULT FALSE,
    original_text TEXT NULL,
    correction_reason TEXT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ingredient_normalizations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    observation_id UUID NOT NULL REFERENCES ingredient_observations(id),
    normalized_text TEXT NOT NULL,
    normalization_method TEXT NOT NULL,
    normalizer_version TEXT NULL,
    confidence NUMERIC NULL,
    status TEXT NOT NULL CHECK (status IN ('complete', 'partial', 'failed')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ingredient_candidates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    normalization_id UUID NOT NULL REFERENCES ingredient_normalizations(id),
    chemical_entity_id UUID NULL REFERENCES chemical_entities(id),
    candidate_name TEXT NOT NULL,
    match_status TEXT NOT NULL,
    candidate_score NUMERIC NULL,
    match_reasons JSONB,
    source_id UUID NULL REFERENCES sources(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS entity_matches (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    normalization_id UUID NOT NULL REFERENCES ingredient_normalizations(id),
    chemical_entity_id UUID NULL REFERENCES chemical_entities(id),
    match_status TEXT NOT NULL CHECK (match_status IN (
        'exact_match', 'strong_match', 'probable_match', 'candidate',
        'ambiguous', 'unresolved', 'no_match', 'invalid_input')),
    identity_confidence TEXT NOT NULL,
    selected_by TEXT NULL CHECK (selected_by IS NULL OR selected_by IN (
        'deterministic', 'source_match', 'manual_review',
        'user_confirmed', 'hybrid')),
    selected_at TIMESTAMPTZ NULL,
    reason_code TEXT NULL,
    review_status TEXT NULL,
    review_notes TEXT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ------------------------------------------------------------------
-- Claim-level evidence (§§25-27)
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS claims (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    chemical_entity_id UUID NULL REFERENCES chemical_entities(id),
    product_id UUID NULL,
    product_label_id UUID NULL,
    entity_role_id UUID NULL,
    claim_type TEXT NOT NULL,
    field_name TEXT NULL,
    claim_value_text TEXT NULL,
    claim_value_numeric NUMERIC NULL,
    claim_value_json JSONB NULL,
    unit TEXT NULL,
    provenance_type TEXT NOT NULL,
    verification_status TEXT NOT NULL CHECK (verification_status IN (
        'verified', 'supported', 'computed', 'provisional', 'candidate',
        'unverified', 'conflicted', 'unknown', 'obsolete')),
    confidence TEXT NOT NULL,
    valid_from TIMESTAMPTZ NULL,
    valid_until TIMESTAMPTZ NULL,
    source_version TEXT NULL,
    freshness_class TEXT NULL,
    last_checked_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS claim_sources (
    claim_id UUID NOT NULL REFERENCES claims(id),
    source_id UUID NOT NULL REFERENCES sources(id),
    support_type TEXT NOT NULL,
    support_strength TEXT NOT NULL,
    source_locator TEXT NULL,
    source_value TEXT NULL,
    review_status TEXT NULL,
    review_notes TEXT NULL,
    provider TEXT NULL,
    source_version TEXT NULL,
    retrieved_at TIMESTAMPTZ NULL,
    response_hash TEXT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (claim_id, source_id)
);

CREATE TABLE IF NOT EXISTS verification_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    claim_id UUID NOT NULL REFERENCES claims(id),
    previous_status TEXT NULL,
    new_status TEXT NOT NULL,
    previous_confidence TEXT NULL,
    new_confidence TEXT NULL,
    review_method TEXT NOT NULL,
    reviewer_type TEXT NOT NULL CHECK (reviewer_type IN (
        'system', 'human', 'researcher', 'admin')),
    reason TEXT NULL,
    source_id UUID NULL REFERENCES sources(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ------------------------------------------------------------------
-- Verification decisions (Stage-7 record; specified by the
-- verification architecture, new to the schema).
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS verification_decisions (
    id UUID PRIMARY KEY,
    entity_match_id UUID NULL REFERENCES entity_matches(id),
    candidate_key TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'verified', 'provisional', 'conflicted',
        'unverified', 'unknown', 'obsolete')),
    identity_confidence TEXT NOT NULL,
    rules_version TEXT NOT NULL,
    snapshot_version TEXT NOT NULL,
    evidence_context_hash TEXT NOT NULL,
    reason TEXT NULL,
    warnings JSONB NULL,
    gate_results JSONB NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ------------------------------------------------------------------
-- Human review (Stage-9 records; new to the schema).
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reviews (
    id TEXT PRIMARY KEY,
    candidate_key TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    normalized_text TEXT NOT NULL,
    identifier TEXT NULL,
    resolution JSONB NOT NULL,
    verification_status TEXT NOT NULL,
    evidence_context JSONB NOT NULL,
    evidence_hash TEXT NOT NULL,
    priority INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'queued', 'in_review', 'approved', 'rejected',
        'needs_more_evidence', 'closed_unknown')),
    reviewer TEXT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS review_events (
    id TEXT PRIMARY KEY,
    review_id TEXT NOT NULL REFERENCES reviews(id),
    event_type TEXT NOT NULL CHECK (event_type IN (
        'ReviewCreated', 'ReviewClaimed', 'ReviewDecisionRecorded',
        'ReverificationTriggered', 'VerificationResultRecorded')),
    actor TEXT NOT NULL,
    reason TEXT NOT NULL,
    previous_state TEXT NULL,
    new_state TEXT NOT NULL,
    evidence_context_hash TEXT NOT NULL,
    rules_version TEXT NOT NULL,
    snapshot_version TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ------------------------------------------------------------------
-- Query-path indexes (§25 of the gate: index actual paths only)
-- ------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_observations_scan
    ON ingredient_observations(scan_id);
CREATE INDEX IF NOT EXISTS idx_normalizations_observation
    ON ingredient_normalizations(observation_id);
CREATE INDEX IF NOT EXISTS idx_candidates_normalization
    ON ingredient_candidates(normalization_id);
CREATE INDEX IF NOT EXISTS idx_matches_normalization
    ON entity_matches(normalization_id);
CREATE INDEX IF NOT EXISTS idx_claims_entity
    ON claims(chemical_entity_id);
CREATE INDEX IF NOT EXISTS idx_claims_status
    ON claims(verification_status);
CREATE INDEX IF NOT EXISTS idx_claim_sources_source
    ON claim_sources(source_id);
CREATE INDEX IF NOT EXISTS idx_verification_events_claim
    ON verification_events(claim_id);
CREATE INDEX IF NOT EXISTS idx_decisions_status
    ON verification_decisions(status);
CREATE INDEX IF NOT EXISTS idx_decisions_candidate
    ON verification_decisions(candidate_key);
CREATE INDEX IF NOT EXISTS idx_reviews_status_priority
    ON reviews(status, priority);
CREATE INDEX IF NOT EXISTS idx_reviews_candidate
    ON reviews(candidate_key);
CREATE INDEX IF NOT EXISTS idx_review_events_review
    ON review_events(review_id);
CREATE INDEX IF NOT EXISTS idx_review_events_created
    ON review_events(created_at);

-- ------------------------------------------------------------------
-- Append-only enforcement: event rows reject UPDATE/DELETE at the
-- database level (application code additionally exposes no mutators).
-- ------------------------------------------------------------------
CREATE OR REPLACE FUNCTION reject_event_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'append-only table: % updates/deletes rejected',
        TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_review_events_immutable ON review_events;
CREATE TRIGGER trg_review_events_immutable
    BEFORE UPDATE OR DELETE ON review_events
    FOR EACH ROW EXECUTE FUNCTION reject_event_mutation();

DROP TRIGGER IF EXISTS trg_verification_events_immutable ON verification_events;
CREATE TRIGGER trg_verification_events_immutable
    BEFORE UPDATE OR DELETE ON verification_events
    FOR EACH ROW EXECUTE FUNCTION reject_event_mutation();

-- ------------------------------------------------------------------
-- RLS: enabled everywhere new. Authenticated role may read audit
-- tables; every write stays with the service role (bypass by
-- design, backend-only). No per-user row policies yet: user_id does
-- not exist on these tables (lands with the auth stage). This is a
-- conservative default, NOT a tested production posture.
-- ------------------------------------------------------------------
ALTER TABLE ingredient_observations ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingredient_normalizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingredient_candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE entity_matches ENABLE ROW LEVEL SECURITY;
ALTER TABLE claims ENABLE ROW LEVEL SECURITY;
ALTER TABLE claim_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE verification_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE verification_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE review_events ENABLE ROW LEVEL SECURITY;

-- Role-dependent hardening applies only where Supabase-style roles
-- exist. On bare Postgres the tables still carry RLS + the
-- immutability triggers; policy provisioning happens wherever the
-- authenticated/anon roles are defined (test setups create them
-- before applying migrations to validate RLS for real).
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated')
       AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        EXECUTE 'REVOKE ALL ON ingredient_observations FROM anon, authenticated';
        EXECUTE 'REVOKE ALL ON ingredient_normalizations FROM anon, authenticated';
        EXECUTE 'REVOKE ALL ON ingredient_candidates FROM anon, authenticated';
        EXECUTE 'REVOKE ALL ON entity_matches FROM anon, authenticated';
        EXECUTE 'REVOKE ALL ON claims FROM anon, authenticated';
        EXECUTE 'REVOKE ALL ON claim_sources FROM anon, authenticated';
        EXECUTE 'REVOKE ALL ON verification_events FROM anon, authenticated';
        EXECUTE 'REVOKE ALL ON verification_decisions FROM anon, authenticated';
        EXECUTE 'REVOKE ALL ON reviews FROM anon, authenticated';
        EXECUTE 'REVOKE ALL ON review_events FROM anon, authenticated';
        EXECUTE 'GRANT SELECT ON claims TO authenticated';
        EXECUTE 'GRANT SELECT ON claim_sources TO authenticated';
        EXECUTE 'GRANT SELECT ON verification_events TO authenticated';
        EXECUTE 'GRANT SELECT ON verification_decisions TO authenticated';
        EXECUTE 'GRANT SELECT ON reviews TO authenticated';
        EXECUTE 'GRANT SELECT ON review_events TO authenticated';
        EXECUTE 'DROP POLICY IF EXISTS audit_read_claims ON claims';
        EXECUTE 'CREATE POLICY audit_read_claims ON claims FOR SELECT TO authenticated USING (true)';
        EXECUTE 'DROP POLICY IF EXISTS audit_read_claim_sources ON claim_sources';
        EXECUTE 'CREATE POLICY audit_read_claim_sources ON claim_sources FOR SELECT TO authenticated USING (true)';
        EXECUTE 'DROP POLICY IF EXISTS audit_read_verification_events ON verification_events';
        EXECUTE 'CREATE POLICY audit_read_verification_events ON verification_events FOR SELECT TO authenticated USING (true)';
        EXECUTE 'DROP POLICY IF EXISTS audit_read_decisions ON verification_decisions';
        EXECUTE 'CREATE POLICY audit_read_decisions ON verification_decisions FOR SELECT TO authenticated USING (true)';
        EXECUTE 'DROP POLICY IF EXISTS audit_read_reviews ON reviews';
        EXECUTE 'CREATE POLICY audit_read_reviews ON reviews FOR SELECT TO authenticated USING (true)';
        EXECUTE 'DROP POLICY IF EXISTS audit_read_review_events ON review_events';
        EXECUTE 'CREATE POLICY audit_read_review_events ON review_events FOR SELECT TO authenticated USING (true)';
    ELSE
        RAISE NOTICE 'supabase roles absent: RLS enabled without role policies';
    END IF;
END $$;
