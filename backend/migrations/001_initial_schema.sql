-- Phase 1 Tables Follow DatabaseSchema.md
-- Enables UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE domains (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code TEXT UNIQUE NOT NULL,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE roles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    domain_id UUID NOT NULL REFERENCES domains(id),
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    taxonomy_version TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE sources (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    publisher TEXT,
    source_type TEXT NOT NULL,
    url TEXT,
    identifier TEXT,
    jurisdiction TEXT,
    language_code TEXT,
    authority_level TEXT NOT NULL,
    license TEXT,
    redistribution_allowed BOOLEAN,
    caching_allowed BOOLEAN,
    publication_date DATE,
    retrieved_at TIMESTAMPTZ,
    last_checked_at TIMESTAMPTZ,
    freshness_class TEXT,
    status TEXT NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE chemical_entities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    preferred_name TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    representation_type TEXT NOT NULL,
    status TEXT NOT NULL,
    formula TEXT,
    molecular_weight NUMERIC,
    molecular_weight_unit TEXT,
    cas_number TEXT,
    pubchem_cid BIGINT,
    chebi_id TEXT,
    inchi TEXT,
    inchikey TEXT,
    smiles TEXT,
    canonical_smiles TEXT,
    isomeric_smiles TEXT,
    chemical_class TEXT,
    superclass TEXT,
    structure_status TEXT,
    structure_source_id UUID REFERENCES sources(id),
    metadata JSONB,
    first_verified_at TIMESTAMPTZ,
    last_verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE ingredient_aliases (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    chemical_entity_id UUID NOT NULL REFERENCES chemical_entities(id),
    alias TEXT NOT NULL,
    alias_type TEXT NOT NULL,
    language_code TEXT,
    region_code TEXT,
    source_id UUID REFERENCES sources(id),
    verified BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(chemical_entity_id, alias)
);
