-- ------------------------------------------------------------------
-- Migration 004: OCR boundary (Stage 16)
--
-- ocr_runs: one immutable row per OCR extraction. The raw OCR text
-- is never updated in place: a provider rerun inserts a new run,
-- and a human correction inserts an ocr_corrections row.
-- ocr_corrections: at most one revision per run (UNIQUE on
-- ocr_run_id, enforced again in the service layer). History is
-- append-only; nothing here is ever updated or deleted by the API.
--
-- No image/document bytes are stored anywhere: document_id is an
-- opaque reference (scan id, storage key). No per-user ownership
-- columns exist yet (same deferred posture as the Stage-10 tables:
-- user_id lands with a future auth stage). Documented, not hidden.
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ocr_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    provider_version TEXT NULL,
    raw_text TEXT NOT NULL,
    ocr_confidence NUMERIC NULL,
    page_metadata JSONB NULL,
    source_reference JSONB NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ocr_corrections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ocr_run_id UUID NOT NULL REFERENCES ocr_runs(id),
    corrected_text TEXT NOT NULL,
    reason TEXT NOT NULL,
    actor TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (ocr_run_id)
);

CREATE INDEX IF NOT EXISTS idx_ocr_runs_document
    ON ocr_runs(document_id);
CREATE INDEX IF NOT EXISTS idx_ocr_corrections_run
    ON ocr_corrections(ocr_run_id);

-- ------------------------------------------------------------------
-- RLS: same posture as migration 003. Writes stay with the service
-- role (bypass by design, backend-only); the authenticated role may
-- read. No per-user row policies yet: user_id does not exist on
-- these tables. This is a conservative default, NOT a tested
-- production posture.
-- ------------------------------------------------------------------
ALTER TABLE ocr_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE ocr_corrections ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated')
       AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        EXECUTE 'REVOKE ALL ON ocr_runs FROM anon, authenticated';
        EXECUTE 'REVOKE ALL ON ocr_corrections FROM anon, authenticated';
        EXECUTE 'GRANT SELECT ON ocr_runs TO authenticated';
        EXECUTE 'GRANT SELECT ON ocr_corrections TO authenticated';
        EXECUTE 'DROP POLICY IF EXISTS audit_read_ocr_runs ON ocr_runs';
        EXECUTE 'CREATE POLICY audit_read_ocr_runs ON ocr_runs FOR SELECT TO authenticated USING (true)';
        EXECUTE 'DROP POLICY IF EXISTS audit_read_ocr_corrections ON ocr_corrections';
        EXECUTE 'CREATE POLICY audit_read_ocr_corrections ON ocr_corrections FOR SELECT TO authenticated USING (true)';
    ELSE
        RAISE NOTICE 'supabase roles absent: RLS enabled without role policies';
    END IF;
END $$;
