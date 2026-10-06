# LabelLens — Development Guide

> Last updated: 2026-10-04

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Prerequisites](#2-prerequisites)
3. [Local Setup](#3-local-setup)
4. [Environment Variables](#4-environment-variables)
5. [Database Setup](#5-database-setup)
6. [Running the Backend](#6-running-the-backend)
7. [Running the Frontend](#7-running-the-frontend)
8. [Development Workflow](#8-development-workflow)
9. [Vertical Slice Process](#9-vertical-slice-process)
10. [Agent Roles and Boundaries](#10-agent-roles-and-boundaries)
11. [Engineering Rules](#11-engineering-rules)
12. [Adding a Data Source](#12-adding-a-data-source)
13. [Schema Change Process](#13-schema-change-process)
14. [Pre-Commit Checklist](#14-pre-commit-checklist)
15. [Deployment](#15-deployment)

---

## 1. Project Overview

LabelLens is a universal product-label intelligence platform supporting food, snacks, beverages, cosmetics, personal care, household products, supplements, and informational pharmaceutical labeling. It lets users photograph a product label, extracts ingredients via OCR, matches them against chemical databases, and returns grounded, science-backed explanations of what those ingredients actually are.

**Core pipeline:**

```
Photo upload → OCR extraction → Ingredient normalization
  → Chemical entity matching → Structure/descriptor lookup
  → Evidence aggregation → Grounded AI explanation
```

**Stack at a glance:**

| Layer | Technology |
|---|---|
| Frontend | Next.js, TypeScript (strict), Tailwind CSS |
| Backend | FastAPI, Python, Pydantic |
| Database | PostgreSQL via Supabase |
| Chemistry | RDKit (Python) |
| Migrations | Versioned SQL files (`001_initial_schema.sql`, …) |
| Frontend hosting | Vercel |
| Backend hosting | Free Python host (e.g. Railway free tier, Render free tier) |

---

## 2. Prerequisites

Install these before doing anything else.

- **Node.js** ≥ 20 and **npm** ≥ 10 (or pnpm/yarn — match what the project uses)
- **Python** ≥ 3.11
- **PostgreSQL** client tools (`psql`) — for running migrations locally
- **RDKit** — install via conda or the `rdkit` PyPI wheel
- **git**

Optional but recommended:

- **Docker** — for running a local Postgres instance without touching Supabase
- A Supabase project (free tier works) for the shared dev/staging database

---

## 3. Local Setup

```bash
# 1. Clone
git clone <repo-url> LabelLens
cd LabelLens

# 2. Backend — create a virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt

# 3. Frontend
cd frontend
npm install
cd ..

# 4. Copy environment templates and fill in values (see section 4)
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
```

---

## 4. Environment Variables

Never commit real secrets. All sensitive values live in `.env` / `.env.local` files that are git-ignored.

### Backend (`backend/.env`)

```
# Database
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/labellens

# Supabase (if using Supabase client directly)
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<key>

# OCR
OCR_PROVIDER=local           # "local" uses Tesseract; "google" uses Vision API
GOOGLE_VISION_API_KEY=       # leave blank when OCR_PROVIDER=local

# Chemistry / external lookups
PUBCHEM_BASE_URL=https://pubchem.ncbi.nlm.nih.gov/rest/pug

# App
ENVIRONMENT=development
ALLOWED_ORIGINS=http://localhost:3000
MAX_UPLOAD_BYTES=5242880     # 5 MB
ALLOWED_MIME_TYPES=image/jpeg,image/png,image/webp
```

### Frontend (`frontend/.env.local`)

```
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

> **Free-first rule:** before adding any paid API key, check whether a free or local alternative exists, verify current rate limits, and estimate actual usage. Do not make continuous paid inference an architectural requirement.

---

## 5. Database Setup

Migrations live in `backend/migrations/` as versioned SQL files (`001_initial_schema.sql`, `002_add_sources.sql`, …). They are applied in order and are always forward-only. Never edit a migration that has already been applied to any shared environment.

### Apply migrations locally

```bash
# Using psql directly
psql "$DATABASE_URL" -f backend/migrations/001_initial_schema.sql
psql "$DATABASE_URL" -f backend/migrations/002_add_sources.sql
# … repeat for each unapplied file in order
```

### Seed reference data

```bash
python backend/scripts/seed_domains_sources.py
```

### Reset (development only)

```bash
psql "$DATABASE_URL" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
# Then re-apply all migrations and re-seed
```

---

## 6. Running the Backend

```bash
source .venv/bin/activate
cd backend
uvicorn app.main:app --reload --port 8000
```

Verify it is up:

```bash
curl http://localhost:8000/health
# Expected: {"data": {"status": "ok", "version": "0.1.0"}}
```

Run backend tests:

```bash
pytest backend/tests/ -v
```

Run type checks:

```bash
mypy backend/app
```

Run lint:

```bash
ruff check backend/
```

---

## 7. Running the Frontend

```bash
cd frontend
npm run dev
```

App is served at `http://localhost:3000`.

Run type checks:

```bash
npm run type-check
```

Run lint:

```bash
npm run lint
```

Run unit tests:

```bash
npm test
```

---

## 8. Development Workflow

Work in **vertical slices** — each slice delivers a complete, testable capability from API to UI before the next slice starts.

### Slice template

Every implementation task must document:

| Field | Description |
|---|---|
| **Goal** | One sentence: what capability this slice adds |
| **Files to change** | Explicit list of files being touched |
| **Acceptance criteria** | Exact, verifiable conditions for "done" |
| **Test cases** | What to test and expected outcomes |
| **Known risks** | Failure modes, edge cases, dependencies |
| **Expected output** | Sample API response, screenshot, or log line |

### Within each slice

```
Research → Schema → API → UI → Tests → Verification → Commit
```

- **Research**: understand the domain (chemistry, OCR quirks, data source format) before writing code.
- **Schema**: if DB changes are needed, write the migration first (see section 13).
- **API**: implement and document the endpoint in `API_SPEC.md` before wiring the UI.
- **UI**: build loading, empty, error, retry, and "not enough information" states — not just the happy path.
- **Tests**: write tests before declaring the slice done.
- **Verification**: run lint + type checks + unit tests + build + key E2E flows.
- **Commit**: small, descriptive commits. Use feature branches for slices that span multiple sessions.

### Never declare done without running

```bash
# Backend
ruff check backend/ && mypy backend/app && pytest backend/tests/ -v

# Frontend
npm run lint && npm run type-check && npm test && npm run build
```

---

## 9. Vertical Slice Process

Implement slices in this order. Do not start a later slice until the earlier one is verified and committed.

| # | Slice | Key deliverables |
|---|---|---|
| 1 | **Health + DB** | `/health` endpoint, DB connection, basic domains/sources data |
| 2 | **Scan** | Create scan, upload validation (type + size), scan retrieval |
| 3 | **OCR** | OCR adapter, OCR run endpoint, OCR result storage |
| 4 | **Ingredient editing** | Ingredient observations, user correction, normalization |
| 5 | **Entity matching** | Candidate lookup, match status, chemical entity retrieval |
| 6 | **Chemistry** | Structure validation, descriptors, chemistry view |
| 7 | **Evidence** | Claims, sources, provenance, confidence scoring |
| 8 | **Analysis** | Complete pipeline, summary, ingredient-level results |
| 9 | **Compare** | Comparison endpoint, shared/unique/ambiguous ingredient sets |
| 10 | **Grounded explanation** | Verified data → AI-generated explanation (grounded, cited) |

Each slice must pass its own acceptance criteria before the next one starts. Partial slices that break earlier slices are not acceptable.

---

## 10. Agent Roles and Boundaries

LabelLens uses multiple AI tools. Each has a defined role. Do not use one agent for another's primary responsibility without a reason.

| Agent | Primary role |
|---|---|
| **ChatGPT** | Architecture decisions, product planning, research synthesis, QA, documentation, presentation, portfolio |
| **Gemini Pro** | Deep research, independent source discovery, image/OCR experiments, dataset investigation, cross-checking facts |
| **OpenCode** | Primary coding agent — implements features, writes tests, refactors |
| **Claude Code** | Debugging, targeted refactoring, code review, test improvement, security review |
| **Hermes Agent (Termux)** | Command execution, orchestration, repeatable workflows, migration runs |
| **GitHub** | Repository, issues, feature branches, checkpoints, changelog |

### Boundary rules

- No agent may silently change API contracts. Any API change requires:
  1. Update `API_SPEC.md`
  2. Implement the code change
  3. Write or update tests
  4. Create a migration if the schema is affected
  5. Add an entry to `CHANGELOG.md` and `DECISIONS.md`

- No agent may introduce a schema change without updating `DATABASE_SCHEMA.md` and creating a numbered migration file.

- When in doubt about a decision, apply the default rule:

  > Choose the path that maximizes **real user utility + scientific correctness + maintainability + demo quality + portfolio value** while minimizing **unnecessary complexity + unsupported claims + hallucination risk + vendor lock-in + fake AI**.

---

## 11. Engineering Rules

### TypeScript / Frontend

- Strict mode is on. No `any` without a comment explaining why.
- All API responses must have typed contracts. Generate or maintain types from `API_SPEC.md`.
- Every data-fetching component must handle: loading, empty, error, retry, and "not enough information" states.
- Optimize for mobile — test at 375px width.
- Avoid heavy animations. Prioritize speed and clarity.

### Python / Backend

- All modules must be independently importable and testable.
- Validate every API input with Pydantic models. Reject invalid input at the boundary.
- Restrict upload types to `image/jpeg`, `image/png`, `image/webp` and enforce the size limit (`MAX_UPLOAD_BYTES`).
- Handle OCR failures gracefully — return a structured error, never a 500.
- Never display an unsupported chemical claim as fact. If confidence is below threshold, surface uncertainty explicitly.
- Maintain sample-label regression tests. Any OCR or matching change must be verified against the sample set.

### General

- Never commit secrets. Use environment variables.
- All environment variables must have an entry in `.env.example` with a safe placeholder value and a comment.
- Keep paid API calls out of the critical path unless there is no viable free alternative (see section 4, free-first rule).

---

## 12. Adding a Data Source

"Data source" means a new external database, API, or dataset used for ingredient lookups, chemical data, or evidence.

1. **Research first.** Use Gemini Pro to verify the source is authoritative, has acceptable licensing, and is actually needed. Check if PubChem or an existing source already covers the data.
2. **Document the decision.** Add an entry to `DECISIONS.md` explaining why this source was chosen over alternatives.
3. **Add to schema.** Insert a row into the `sources` table via a new migration. See section 13.
4. **Implement the adapter.** Create `backend/app/adapters/<source_name>.py`. The adapter must be independently testable with mocked HTTP.
5. **Register the source.** Add the adapter to the source registry so the entity-matching layer can use it.
6. **Write tests.** Unit tests for the adapter, plus at least one integration test against a real (or recorded) response.
7. **Update `API_SPEC.md`** if a new endpoint or response field is introduced.
8. **Add a domain entry** (`domains` table) if the source covers a new evidence domain.

---

## 13. Schema Change Process

Never modify a migration file that has already been applied to any shared environment (dev, staging, production).

### Steps

1. **State the reason.** Write a one-paragraph explanation of why the change is needed.
2. **Identify affected tables.** List every table being added, altered, or dropped.
3. **Write the migration.** Create `backend/migrations/<next_number>_<description>.sql`. The file must be idempotent where possible (`CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`).
4. **Write the rollback.** Create a matching `<next_number>_<description>_rollback.sql` unless rollback is genuinely impossible (e.g. destructive data loss).
5. **Check backward compatibility.** If any existing API endpoint returns data from the changed table, confirm the response shape is unchanged or update the endpoint and its spec simultaneously.
6. **Update `DATABASE_SCHEMA.md`.** Reflect the new state of every affected table.
7. **Write tests.** At minimum, verify the migration applies cleanly from the previous state and that rollback returns to it.
8. **Record in `DECISIONS.md`.** Include: reason, affected tables, migration file name, backward compatibility note, rollback plan.
9. **Apply and verify locally** before opening a PR.

---

## 14. Pre-Commit Checklist

Run this before every commit that touches backend or frontend code.

```
Backend
  [ ] ruff check backend/         — no lint errors
  [ ] mypy backend/app            — no type errors
  [ ] pytest backend/tests/ -v    — all tests pass
  [ ] Sample-label regression set passes (if OCR or matching changed)

Frontend
  [ ] npm run lint                 — no lint errors
  [ ] npm run type-check           — no type errors
  [ ] npm test                     — all tests pass
  [ ] npm run build                — build succeeds

Both
  [ ] No secrets or .env files staged (git diff --cached)
  [ ] If API contract changed: API_SPEC.md updated
  [ ] If schema changed: migration file + DATABASE_SCHEMA.md + DECISIONS.md updated
  [ ] CHANGELOG.md entry added for meaningful changes
  [ ] PR / commit message describes the "why", not just the "what"
```

---

## 15. Deployment

### Frontend (Vercel)

Vercel deploys automatically on push to `main`. Preview deployments are created for every PR.

- Production environment variables are set in the Vercel dashboard — never in committed files.
- The `NEXT_PUBLIC_API_BASE_URL` variable must point to the deployed backend URL in production.

### Backend (free Python host)

The backend is deployed to a free-tier Python host (Railway, Render, or equivalent). Deployment is triggered by push to `main` or via the host's CLI.

```bash
# Example: Render deploy via CLI
render deploy --service <service-id>
```

- The `DATABASE_URL` and all other secrets are set as environment variables in the hosting dashboard.
- Run pending migrations against the production database before the new backend version goes live:

  ```bash
  # From a secure environment with DATABASE_URL set to production
  psql "$DATABASE_URL" -f backend/migrations/<new_migration>.sql
  ```

- Verify the health endpoint after every production deploy:

  ```bash
  curl https://<backend-domain>/api/v1/health
  ```

### Backend staging (Cloud Run, Stage 18.5)

Staging deploys the Docker image to Cloud Run (`asia-south1`)
instead of a generic Python host; the Railway/Render sketch
above remains an alternative, not the plan of record. Install
with test extras locally (`pip install -e ".[test]"`); production
images install the base set only. Before deploying: apply
migrations explicitly (`scripts/migrate_staging.sh`), never on
boot; staging requires `ENVIRONMENT=production` plus a real
`DATABASE_URL` or `app.serve` refuses to start. Smoke with
`scripts/smoke_staging.py` (needs operator JWTs; never in CI).
Full procedure: `STAGE_18_5_DEPLOYMENT.md`.

### Rollback

If a deploy breaks the health check or key E2E flows:

1. Revert the Vercel or host deployment to the previous release via the dashboard.
2. If a migration was applied: run the rollback SQL file against the production database.
3. Open a GitHub issue with the failure details before attempting a fix.

---

*For architectural decisions and historical context, see `DECISIONS.md`. For the complete API reference, see `API_SPEC.md`. For the database layout, see `DATABASE_SCHEMA.md`.*
