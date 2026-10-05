-- Seed Domains
INSERT INTO domains (id, code, name, description) VALUES
  ('11111111-1111-1111-1111-111111111111', 'food', 'Food', 'Food ingredients and additives'),
  ('22222222-2222-2222-2222-222222222222', 'snacks', 'Snacks', 'Snack product ingredients'),
  ('33333333-3333-3333-3333-333333333333', 'beverages', 'Beverages', 'Beverage ingredients'),
  ('44444444-4444-4444-4444-444444444444', 'cosmetics', 'Cosmetics', 'Cosmetic ingredients'),
  ('55555555-5555-5555-5555-555555555555', 'personal_care', 'Personal Care', 'Personal care ingredients'),
  ('66666666-6666-6666-6666-666666666666', 'household', 'Household', 'Household product ingredients'),
  ('77777777-7777-7777-7777-777777777777', 'supplement', 'Supplement', 'Dietary supplements'),
  ('88888888-8888-8888-8888-888888888888', 'pharma', 'Pharma', 'Informational pharmaceutical labeling'),
  ('99999999-9999-9999-9999-999999999999', 'other', 'Other', 'Other domains')
ON CONFLICT DO NOTHING;

-- Seed Sources
INSERT INTO sources (id, name, source_type, authority_level, status) VALUES
  ('a1111111-1111-1111-1111-111111111111', 'PUBCHEM', 'scientific_database', 'high', 'approved'),
  ('b2222222-2222-2222-2222-222222222222', 'CHEBI', 'scientific_database', 'high', 'approved'),
  ('c3333333-3333-3333-3333-333333333333', 'NIST_WEBBOOK', 'scientific_database', 'high', 'conditional'),
  ('d4444444-4444-4444-4444-444444444444', 'RDKIT', 'software_methodology', 'high', 'approved'),
  ('e5555555-5555-5555-5555-555555555555', 'FSSAI_FOOD_REGS', 'regulatory', 'high', 'approved'),
  ('f6666666-6666-6666-6666-666666666666', 'CODEX_GSFA', 'regulatory', 'high', 'approved'),
  ('g7777777-7777-7777-7777-777777777777', 'EU_FOOD_ADDITIVES', 'regulatory', 'high', 'approved'),
  ('h8888888-8888-8888-8888-888888888888', 'FDA_FOOD_ADDITIVES', 'regulatory', 'high', 'approved'),
  ('i9999999-9999-9999-9999-999999999999', 'EU_COSING', 'informational', 'high', 'approved')
ON CONFLICT DO NOTHING;
