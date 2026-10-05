# LabelLens — Implementation Audit

**Date:** 2026-10-05
**Branch:** `feat/label-pipeline-foundation`
**Auditor:** Implementation agent (read-only inspection + baseline test run)
**Scope:** Full repository reality check BEFORE any major implementation, per master brief §2 / §21.

> Rule honored: no major rewrite before audit. Only change so far is creating the feature
> branch. Baseline verification: `pytest backend/app/tests -v` → **1 passed**.

---

## 0. Headline finding — brief vs repository mismatch (must read first)

The master brief describes the repository as a **Vite/React Google AI Studio prototype** with
existing files such as:

- `src/lib/parsing/ingredientParser.ts`
- `src/lib/normalization/ingredientNormalizer.ts`
- `src/lib/entity-resolution/entityResolver.ts`
- `src/lib/pipeline.ts`
- `src/services/labelExtractionService.ts`
- `src/services/webResearchService.ts`
- full UI screens (Home, Scan, Product Analysis, Compare, Catalog/Search, Learn, …)

**None of those files exist in the cloned repository.**

Verified by `ls -laR frontend/`, `find`, and `git log --stat`:

- `frontend/` contains only two **empty** directories: `frontend/src/lib/api/` and
  `frontend/src/types/`. No `package.json`, no components, no router, no styles.
- `backend/app/` contains only a health endpoint, config, CORS setup, one Pydantic schema,
  and one unit test. No parsing, normalization, entity-resolution, pipeline, OCR,
  web-research, chemistry, evidence, or comparison code.
- Git history has exactly **2 commits**: `Phase 1: Core Foundation` (specs + skeleton) and
  `Fix flake8 styling`.
- No remote is configured (`git remote -v` returns empty), so
  `amithsharma91/LableLens` could not be cross-checked from here.

**Consequence:**

1. There is **no product UI to preserve** in this checkout. §14 of the brief
   ("do not downgrade the current visual product") is vacuously satisfied — there is
   nothing to downgrade, but also nothing to leverage.
2. There is **no duplicated/conflicting ingredient logic to unify yet** (§2D). That section
   of the brief is written against a different codebase state. The audit answers it as
   "not applicable — greenfield", which is actually good news: we can establish **one**
   canonical pipeline from the start instead of untangling three.
3. `INGREDIENT_GOLDEN_DATA.csv` (100 rows) is correctly marked `needs_verification` with
   **all chemistry fields empty** — it is a candidate seed, not ground truth. The brief's
   warning is accurate and must be kept.
4. `LABEL_REGRESSION_DATASET.csv` (30 rows, LR-001…LR-030) is a **scaffold with no label
   text at all** — every row is `needs_real_label`. It cannot be used as a correctness
   benchmark until real labels are ingested.

If a richer prototype exists elsewhere (another branch, another repo, a local export),
it should be added to this repo or the brief should be amended. Until then, all
"preserve the prototype" requirements are recorded as **blocked on missing input**,
and implementation proceeds on the **spec-defined target stack**
(Next.js + FastAPI + RDKit + Supabase) starting from the existing FastAPI skeleton.

---

## A. Repository reality

| Area | Finding | Evidence |
|---|---|---|
| Framework (backend) | **FastAPI + Pydantic v2**, async SQLAlchemy + asyncpg | `backend/app/main.py`, `config.py`, `dependencies.py`, `pyproject.toml` |
| Framework (frontend) | **Intended Next.js + TypeScript + Tailwind** per specs; **actually empty dirs**, no `package.json`, no code | `ls -laR frontend/` → only empty `lib/api`, `types` |
| Runtime | Python **3.13.5**, Node **v26.4.0**, npm **11.19.1** | `python3 --version`, `node --version` |
| Build system (backend) | `pyproject.toml` with pytest config only (`testpaths=["app/tests"]`, `asyncio_mode=auto`). **No** `requirements.txt`, no ruff/mypy config, no Dockerfile, no CI workflow | `backend/pyproject.toml`, repo root listing |
| Build system (frontend) | **None** — no `package.json`, no `tsconfig`, no Tailwind config, no Next.js scaffold | `find` for `package.json`/`*.ts` → no hits outside `.venv` |
| Dependency state (backend venv) | fastapi 0.142, uvicorn, pydantic 2.13, pydantic-settings, SQLAlchemy 2.1, asyncpg, httpx, pytest 9.1 + pytest-asyncio, flake8. **No RDKit, no OCR lib, no Gemini/OmniRoute SDK, no Supabase client** | `pip list` in `backend/.venv` |
| Frontend architecture | **Does not exist.** Spec target (`lib/api/client.ts`, `scans.ts`, … + `types/api.ts`) is documented in `ARCHITECTURE.md` §4 but not implemented | empty `frontend/src` |
| Backend architecture | Skeleton only: `main.py` (CORS + router mount) → `api/v1/health.py` → `schemas/common.py`. `providers/`, `repositories/`, `services/` directories exist but are **empty**. `config.py` reads `DATABASE_URL`, `ALLOWED_ORIGINS` | `ls -laR backend/app` |
| API endpoints | Exactly **2**: `GET /` and `GET /api/v1/health` (returns `{data:{status:"ok",version:"0.1.0"}}`) | `main.py`, `health.py`, `test_health.py` |
| Environment variables | Backend reads `ENVIRONMENT`, `LOG_LEVEL`, `ALLOWED_ORIGINS`, `DATABASE_URL` (default local postgres). **No `.env` or `.env.example` files exist** in repo. Required vars from specs (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `MAX_UPLOAD_BYTES`, `OCR_PROVIDER`, `AI_PROVIDER`, `PUBCHEM_BASE_URL`, …) are **not wired** | `config.py`, `find -name "*.env*"` → none |
| Current persistence | **None live.** Migrations `001_initial_schema.sql` (domains, roles, sources, chemical_entities, ingredient_aliases) and `002_seed_data.sql` (9 domains, 9 sources) exist but there is **no evidence they were ever applied** (no DB URL reachable here, no seed script, no repository code, no Supabase project reference) | `backend/migrations/*` |
| Current data sources | **None wired.** No PubChem/ChEBI/Codex/FSSAI/CosIng adapters, no local golden cache, no source-registry table access code | empty `providers/`, `repositories/` |
| Current testing | **1 test**: `test_health_endpoint` (ASGI transport, asserts 200 + status ok). **Passes.** No unit/integration/contract/E2E/regression/golden tests | `app/tests/unit/test_health.py`, pytest run 2026-10-05 |
| Docs | 17 Markdown specs + 2 CSVs present and internally consistent (see `IMPLEMENTATION_READINESS_REPORT.md`, `DOCUMENTATION_COVERAGE_REPORT.md`). `CHANGELOG.md` is at v0.1.1 (docs only, "No implementation code shipped") — accurate | root listing, `CHANGELOG.md` |
| Git hygiene | `master` clean; feature branch `feat/label-pipeline-foundation` created for this work. **Problem: `__pycache__/*.pyc` files are committed** (both commits include them). No `.gitignore` observed | `git log --stat`, `git status` |
| Deployment | **Nothing deployed.** No Vercel/Render/Railway config, no Dockerfile, no CI YAML | repo root listing |

---

## B. Feature status

Legend: WORKING / PARTIAL / MOCKED / BROKEN / MISSING / NEEDS VERIFICATION.

### User-facing surfaces

| Feature | Status | Notes |
|---|---|---|
| Home | **MISSING** | No frontend code at all |
| Scan | **MISSING** | No upload endpoint, no camera UI |
| Upload | **MISSING** | No `POST /api/v1/scans`, no multipart handling |
| Camera/file handling | **MISSING** | — |
| OCR | **MISSING** | No adapter, no `ocr_runs` table (Phase 2 table not yet migrated) |
| OCR error handling | **MISSING** | — |
| Raw OCR preservation | **MISSING** | No `ocr_runs` / `ingredient_observations` tables or code; spec contract defined in `DATA_PIPELINE.md` Stage 1 only |
| Ingredient extraction | **MISSING** | No parser of any kind (naive or hierarchical) |
| Hierarchical parsing | **MISSING** | ← **highest-value first implementation (this branch)** |
| Manual text entry | **MISSING** | — |
| Editing / deletion / reordering | **MISSING** | No observation endpoints |
| Nested ingredient handling | **MISSING** | — |
| Percentages | **MISSING** | — |
| Additive identifiers (INS/E) | **MISSING** | — |
| Normalization | **MISSING** | No normalizer code; 6-method taxonomy defined in specs only |
| Entity resolution | **MISSING** | No matcher; resolution states defined in specs only |
| Local catalog matching | **MISSING** | `chemical_entities` + `ingredient_aliases` tables defined in migration but no data, no lookup code |
| Mixture handling | **MISSING** | Representation-type taxonomy defined in specs only |
| Ambiguous ingredient handling | **MISSING** | — |
| Web research fallback | **MISSING** | No Gemini/OmniRoute integration, no `webResearchService` |
| Source extraction / provenance | **MISSING** | `sources` table defined in migration; no claim/source code |
| Confidence (multi-dimensional) | **MISSING** | Vocabulary defined in specs; no code |
| Ingredient detail | **MISSING** | No `GET /api/v1/ingredients/{id}`, no UI |
| Chemistry representation | **MISSING** | No RDKit, no formula/MW/SMILES code |
| RDKit integration | **MISSING** | `import rdkit` → `ModuleNotFoundError`. Not in `pyproject.toml` |
| Product analysis | **MISSING** | No analysis pipeline, no `analysis_runs` tables |
| Compare | **MISSING** | No comparison endpoints, no UI |
| Actual scan-to-compare flow | **MISSING** | E2E critical path (`API_SPEC.md` §77) has zero coverage |
| Persistence | **PARTIAL** | Phase-1 DDL + seeds exist on disk, unapplied; app never connects (engine created in `dependencies.py` but no route uses `get_db`) |
| Authentication | **MISSING** | No auth; acceptable per spec (MVP may operate without accounts) |
| Security (upload/MIME/rate-limit/prompt-injection/RLS) | **MISSING** | No upload path to secure yet; CORS is the only control present (`ALLOWED_ORIGINS`, `allow_credentials=True` — note §F finding below) |
| Testing | **PARTIAL** | Health test WORKING; everything else MISSING (see §F) |
| Deployment | **MISSING** | No frontend/backend deploy config |

### Backend slice status (per `DEVELOPMENT_GUIDE.md` §9 vertical slices)

| Slice | Status |
|---|---|
| 1 Health + DB | **PARTIAL** — health WORKING; DB DDL on disk, not applied, no DB test |
| 2 Scan | MISSING |
| 3 OCR | MISSING |
| 4 Ingredient editing | MISSING |
| 5 Entity matching | MISSING |
| 6 Chemistry | MISSING |
| 7 Evidence | MISSING |
| 8 Analysis | MISSING |
| 9 Compare | MISSING |
| 10 Grounded explanation | MISSING |

---

## C. Trace the actual scan pipeline

There is **no scan pipeline in code**. The intended pipeline (per `DATA_PIPELINE.md`,
`ARCHITECTURE.md` §6) vs reality:

```
Stage                              Spec contract              Code reality
─────────────────────────────────  ─────────────────────────  ──────────────
1  OCR (raw_text, conf, engine)    DATA_PIPELINE §Stage 1     MISSING — no endpoint, no ocr_runs table
2  Extraction (raw → tokens)       §Stage 2                   MISSING — no parser at all
3  User correction (non-destr.)    §Stage 3                   MISSING — no PATCH endpoint
4  Normalization (6 methods)       §Stage 4                   MISSING
5  Entity resolution (6 states)    §Stage 5                   MISSING
6  Validation gates                §Stage 6                   MISSING
7  RDKit computation (gated)       §Stage 7                   MISSING (rdkit not installed)
8  Role resolution (domain ctx)    §Stage 8                   MISSING
9  Evidence assembly (claim-lvl)   §Stage 9                   MISSING
10 Grounded explanation            §Stage 10                  MISSING
```

Executable code path today:

```
GET /api/v1/health → HealthResponse(data={status:"ok", version:"0.1.0"})
```

That is the entire backend. `dependencies.py` builds an async engine from
`DATABASE_URL`, but no router, service, or repository imports it.

---

## D. Duplicated / conflicting logic

**Not applicable — no duplication exists because no logic exists.**

The brief's §D checklist is answered against an empty set:

- [ ] OCR segmenting ingredients? No OCR code.
- [ ] `labelExtractionService.ts` extra parsing? File does not exist.
- [ ] `parseRawLabelText()` naive comma split? Function does not exist.
- [ ] `parseIngredientTree()` used consistently? Function does not exist.
- [ ] `pipeline.ts` canonical path? File does not exist.
- [ ] UI bypassing canonical pipeline? No UI.
- [ ] Normalization in multiple places? No normalizer.
- [ ] Entity matching in multiple places? No matcher.

**Architectural decision recorded for the build-out (see `DECISIONS.md` ADR-016
proposed): exactly ONE canonical extraction entry point —
`backend/app/services/ingredient_parser.py :: parse_label_ingredients(text)` —
returning a tree of nodes. All future paths (OCR post-processing, manual-text entry,
re-analysis after correction, tests, seed scripts) must call it. No UI/service may
implement its own `split(",")`. This audit establishes that rule before the first
competing implementation appears.**

---

## E. Scientific integrity audit

No chemistry-fabrication code exists yet (nothing to flag in `grep` terms — there is
no `smiles`, `cas`, `formula`, `safe`, `healthy` string anywhere in `backend/app` or
`frontend/src` outside specs). The risk is therefore **prospective**, and the audit
converts each brief §E bullet into a build-time gate:

| Risk | Current state | Gate for future code |
|---|---|---|
| Invent chemical identity / formula / SMILES / CAS | No code paths; golden CSV has all such fields **empty** (good) | Parser/normalizer/matcher must never populate chemistry fields; only a future verified-source adapter + RDKit gate may. Parser nodes carry `matchStatus="unresolved"`, `verificationStatus="unverified"` by construction |
| Assign structure to a mixture | No structures anywhere | `representation_type` allowlist enforced at parse→chemistry boundary; mixtures (`peanut butter`, `whey protein concentrate`, `lecithin`, `fragrance`, …) stay structureless |
| Claim regulatory verification without evidence | No regulatory code | Jurisdiction + source + date required per `SOURCE_REGISTRY.md`; no `verified` status without them |
| Treat AI text as verified fact | No AI integration | AI outputs enter only as `candidate` (ADR-007); no AI-writes-to-canonical path |
| Umbrella term → single molecule | No resolver | Resolver must return `ambiguous`/`no_match` for `natural flavouring`, `colour`, `spices`, etc. |
| "good/bad/safe/unsafe/healthy" labels | No UI copy | Banned vocabulary in analysis/explanation outputs; comparison must not rank products |

The canonical parser implemented on this branch is deliberately **chemistry-free**:
it extracts structure (nesting, percentages, identifiers) and performs only
**syntactic** normalization (case/whitespace/punctuation). It does not guess entities,
formulas, or roles. That separation is the primary anti-hallucination control at this
layer.

---

## F. Dependency / runtime / security / testing findings

1. **Python deps (installed):** fastapi, uvicorn, pydantic-settings, SQLAlchemy, asyncpg,
   pytest, pytest-asyncio, httpx, flake8. All import cleanly on Python 3.13.
2. **Missing for target stack:** `rdkit` (deliberately **not** added in this slice —
   parser needs no chemistry; RDKit arrives with the chemistry slice and its Dockerfile
   story, per `IMPLEMENTATION_READINESS_REPORT.md` risk #3), OCR libs, Supabase client,
   rate-limit lib (`slowapi`), image libs (Pillow). `pyproject.toml` has **no**
   `[tool.ruff]`/`[tool.mypy]` sections and no `requirements.txt` — reproducible pinning
   is a gap to fix before deployment (not blocking for parser slice).
3. **Frontend toolchain:** none. Initializing Next.js is explicitly **deferred** — no UI
   work is justified until the scan→analysis contract has a backend to talk to.
4. **Committed `.pyc` files:** `__pycache__/*.pyc` are tracked in git (both commits).
   Add `.gitignore` (Python + Node + `.env`) and untrack them — hygiene fix queued with
   this branch's commits.
5. **CORS note:** `allow_credentials=True` combined with `allow_headers=["*"]` is fine
   for local dev with an explicit origin allowlist, but production must restrict
   `allowed_origins` to the Vercel domain and avoid credentialed wildcard patterns
   (spec `SECURITY.md` §10). No change needed yet — no authenticated endpoints exist.
6. **No secrets in repo:** confirmed (`find -name "*.env*"` → none; `config.py` uses
   env vars with safe defaults). Keep it that way; add `.env.example` files when the
   DB/AI slices land.
7. **Testing gaps:** 1/1 passing. Missing per `TEST_STRATEGY.md`: parser unit tests
   (Cases A–J — **added this branch**), normalization/matcher/chemistry unit tests,
   API contract tests, DB integration tests (need test DB), E2E critical path,
   regression dataset (blocked on real labels), golden verification (blocked on source
   lookups). Coverage gates (≥80% changed files) cannot be measured — no coverage tool
   configured yet.

---

## G. Prioritized implementation plan (smallest safe sequence)

Executed and proposed order. Each item is independently verifiable.

| # | Step | Status | Verification |
|---|---|---|---|
| 0 | This audit (`IMPLEMENTATION_AUDIT.md`) | **Done (this file)** | Review against brief §2 A–E |
| 1 | Canonical hierarchical parser + Cases A–J tests (`services/ingredient_parser.py`, `tests/unit/test_ingredient_parser.py`) | **In progress on this branch** | `pytest` green; flake8 clean; no chemistry fields populated |
| 2 | `.gitignore` + untrack `__pycache__`; `CHANGELOG.md` entry | With this branch | `git status` clean of `.pyc`; changelog diff |
| 3 | Normalization service (syntactic only, Stage 4) + unit tests | Next | Tests: case/whitespace/punct, INS/E extraction preserved, OCR-artifact flagging; identity-change tests must fail if normalizer alters chemistry |
| 4 | Deterministic entity-resolution skeleton against local alias table (exact → normalized → alias → candidate → unresolved; never promote ambiguous) | Next | Golden-candidate fixtures (not golden-truth assertions) |
| 5 | OCR adapter interface + `ocr_runs` migration (Phase 2 tables) + raw-text preservation tests | Next | Poor/unusable confidence blocks silent analysis |
| 6 | Supabase/local-Postgres wiring + apply migrations 001/002 + DB integration test | Next | Requires `DATABASE_URL_TEST`; blocked until a test DB exists |
| 7 | RDKit chemistry gate (only after verified SMILES exists; mixtures rejected) | Later | Needs Dockerfile/pinning decision (readiness-report risk #3) |
| 8 | Evidence/claims + roles + analysis + compare + grounded explanation | Later, in vertical-slice order (`DEVELOPMENT_GUIDE.md` §9) | Contract tests per `API_SPEC.md` §76 |
| 9 | Next.js frontend scaffold | **Deferred** until slices 1–5 have stable contracts to code against | — |

Out of scope for this branch by design: migrations, DB connection, RDKit install,
frontend scaffold, AI integration, deployment config.

---

## H. Remaining risks / explicit non-claims

- This audit **does not claim** production readiness, OCR accuracy, chemical coverage,
  or deployment test results — none exist yet.
- Parser tests use **synthetic label strings**, not real labels; `LABEL_REGRESSION_DATASET.csv`
  remains `needs_real_label` and is not asserted against.
- No typecheck/lint/build beyond `pytest` + `flake8` + `python -m compileall` — frontend
  gates are N/A (no frontend), `mypy`/`ruff` are not configured in this repo.
- If the "Google AI Studio prototype" referenced by the brief is produced later, a
  second audit pass is required to reconcile it with this canonical pipeline before
  merging any of its logic.

---

*End of audit. Implementation proceeds with Step 1 (canonical parser) on this branch.*
