# Stage 18.5 — Staging Deployment (backend on Cloud Run)

Date: 2026-10-06
Status: **PARTIAL** — all deployment artifacts, procedures, and
local validation are complete; the actual Cloud Run deployment was
not executed because this environment has no Google Cloud
credentials, no GCP project, and no Supabase staging credentials
(see §18). Nothing below claims an unexecuted deployment.

Stage 19 RDKit must still wait: this stage gates it, complete or
not, and the gate output is this document plus the artifacts.

---

## 1. Deployment architecture

```text
(future) Next.js on Vercel
        ↓ HTTPS (browser; CORS allow-listed origin only)
Google Cloud Run — labellens-api-staging (asia-south1, max 1)
  FastAPI via uvicorn app.serve:app (single worker)
        ↓ asyncpg, NullPool, per-request connection+transaction
Supabase PostgreSQL (+ Auth JWKS for JWT verification)
        ↓ (only when configured)
OCR.space (server-side extraction, optional)
```

Single worker + max 1 instance is load-bearing, not incidental:
the rate limiter is process-local by design, so one process keeps
budgets exact. Multi-instance scaling requires a shared limiter
first (unchanged Stage-12 constraint, repeated in §13).

## 2. Selected host / region

Google Cloud Run, region `asia-south1`, service
`labellens-api-staging`. No project ID is hard-coded anywhere;
`PROJECT_ID` is a required script argument. No GCP project,
billing account, Artifact Registry repo, or service account was
created from here (no credentials exist here to create them).

## 3. Deployment command/procedure

```bash
PROJECT_ID=<gcp-project> ./scripts/deploy_staging.sh
```

Build: `gcloud builds submit` from the repo root
(`backend/Dockerfile`, context includes `snapshots/`).
Deploy: managed Cloud Run, public invocation (so the app's own
JWT boundary is externally testable), min 0 / max 1, 1 vCPU,
512Mi, 60s timeout, concurrency 20, `ENVIRONMENT=production`,
empty `ALLOWED_ORIGINS`, secrets via `--update-secrets` (never
env values, never printed; `set -x` stays off).

## 4. Docker image details

`backend/Dockerfile` (`python:3.13-slim`): system CA certs only;
`pip install /srv/backend` WITHOUT the `[test]` extra (pytest
stays out of the image); `backend/app`, `backend/migrations`,
and `snapshots/` copied to preserve the repo-relative layout the
snapshot adapter expects; non-root `appuser`; workdir
`/srv/backend`; `uvicorn app.serve:app --host 0.0.0.0 --port
${PORT:-8080} --workers 1`. `.dockerignore` drops venvs, caches,
`.env`, git, frontend, markdown, and test files. Dependency
versions resolve fresh at build; a generated constraints file for
byte-reproducible builds is documented follow-up work (the wheel
build + base/test extras split were validated locally).

## 5. Environment variables

Non-secret (plain env): `ENVIRONMENT=production`,
`ALLOWED_ORIGINS=` (empty until the Vercel origin exists),
`LOG_LEVEL=info`. Secrets (Secret Manager only, referenced by
`--update-secrets`): `DATABASE_URL` (service-role/owner URL with
`?ssl=require`), `SUPABASE_URL`, optionally `OCR_SPACE_API_KEY`.
`DEV_API_TOKENS` must be absent (the app refuses to boot with it
under production). No `SUPABASE_JWT_*` overrides are needed:
issuer/JWKS derive from `SUPABASE_URL`.

## 6. Secret handling

Secrets are never committed (template placeholders only),
never baked into the image (`.dockerignore` excludes `.env`;
no `ENV` secret in the Dockerfile), never printed (deploy
script avoids `set -x`; smoke script asserts absence;
`_safe_detail` names host/db only), never returned (no endpoint
emits them; OpenAPI test below), never stored (no credential
column anywhere). Verified by `git grep` scan (§17) and the
`test_openapi_has_no_secrets`-style assertions.

## 7. Database migration procedure

`scripts/migrate_staging.sh [--check|--baseline]` against
`DATABASE_URL` (psql, `ON_ERROR_STOP`, deterministic
001→006 order, `schema_migrations` ledger):

- default: apply unrecorded files each in its own transaction,
  record on success, stop on first failure, then verify
  (8 owner columns + 8 owner RLS policies expected).
- `--check`: verify-only, lists recorded vs pending.
- `--baseline`: for adopting an existing schema — verifies the
  full expected schema FIRST, records only on success, else
  refuses.
- Re-running after success is a verified no-op.
- Forward-only: no destructive rollback SQL exists by design.

Verified locally: fresh database (exit 0, 8+8 checks pass),
idempotent re-run (exit 0, all skipped), `--check` (exit 0),
`--baseline` on a ledger-less complete schema (exit 0).
Run BEFORE first deploy and on every new migration; never on
container boot. Uses the existing Supabase database; no second
database; never the local test database.

## 8. Health/readiness

`GET /api/v1/health` is pure liveness (`{"status":"ok"}`,
version, no secrets, no DB touch, no expensive work) — verified
safe for any prober. There is deliberately NO public DB-touching
readiness endpoint: liveness stays cheap, and database health is
proven by the authenticated smoke checks (§15). A DB connectivity
check (`SELECT 1`) runs once inside the ASGI lifespan at startup
— awaited, never via `asyncio.run()`, which crashes under
Uvicorn's already-running loop (Render startup fix; the factory
itself stays synchronous and import-safe). A dead database fails
startup loudly instead of serving degraded verification; the
engine is disposed on shutdown.

## 9. CORS

Env-driven origins, methods limited to GET/POST/OPTIONS,
credentials allowed (required for future authenticated browser
use, which forbids wildcard origins — so none is used). Staging
ships `ALLOWED_ORIGINS` empty: no browser origin is accepted
until the Vercel frontend exists and its exact origin is added.
Server-to-server and curl smoke tests are unaffected by CORS.

## 10. Authentication

Staging boots only with `ENVIRONMENT=production`
(`app.serve` refuses anything else) plus a reachable database.
`build_token_verifier` then requires Supabase issuer/JWKS config
and refuses `DEV_API_TOKENS` — both covered by construction
tests. Empty `SUPABASE_REVIEWER_SUBJECTS` means nobody reviews
(fail-closed, not a fallback). No auth behavior was weakened;
no new auth code was needed.

## 11. RLS

Migrations carry the policies; `migrate_staging.sh` verifies
8 owner columns + 8 owner RLS policies after applying.
Authenticated writes are denied everywhere; the service role
bypasses by design. Owner/subject isolation is proven locally
(Stage-18 tests) and re-proven remotely by the smoke checks
(§15 items 4–6).

## 12. Rate limiter limitation

Unchanged code. Staging pins max 1 instance + 1 worker so the
process-local budgets stay exact; 429 + `Retry-After` behavior
is a smoke item (§15 item 11, opt-in to avoid junk rows).
Production multi-instance scaling is blocked on a shared
limiter — documented here and in code, not silently assumed.

## 13. OCR provider configuration

Unconfigured by default: the app deploys and serves fully on
the client-text path (`provider: "client"` + FakeOCRProvider
where injected). With `OCR_SPACE_API_KEY` set, `serve.py`
injects `{"ocr-space": …}`; the key never appears in output,
logs, rows, or docs. Live smoke (exactly one controlled call)
happens only if an operator sets the key AND runs
`app.cli.ocr_provider_smoke` explicitly. Not configured here;
reported as NOT CONFIGURED, never as success.

## 14. Smoke tests

`scripts/smoke_staging.py` (stdlib only; unit-tested offline
against a fake opener, including a leak-detection control):
health shape + no secrets; 401 without/invalid auth; owner
create/analyze/correct/verification-lookup; Stage-15 glycerol
VERIFIED/HIGH through auth+API+DB; cross-user 404s on run,
correction, analysis, and verification views; optional
rate-limit 429 + Retry-After; envelope + `X-Request-ID` shape on
every response. Fixed published label text only; JWTs from
`SMOKE_JWT_USER_A/B` env (never printed); exit non-zero unless
everything enabled passes. **Not executed: no deployment exists
to run them against.**

## 15. Rollback procedure

- Application: `gcloud run services update-traffic
  labellens-api-staging --to-revisions <PREV>=100` (each deploy
  creates an immutable revision; image tags are commit SHAs).
  To stop traffic immediately: `--to-revisions` with 0 or
  `gcloud run services delete` (destroys the endpoint; data
  untouched).
- Migrations are forward-only: rolling back code never rolls
  back schema. All six migrations are additive/conditional; a
  bad migration is repaired by a new forward migration, never
  by destructive rollback SQL (none exists by design).
- Data recovery: Supabase point-in-time recovery (project
  setting, outside this repo) — no repo script deletes data.

## 16. Cost-control settings

Scale-to-zero (min 0, request billing), max 1 instance, 1 vCPU,
512Mi, 60s timeout, concurrency 20. No Redis, no Cloud SQL, no
always-on services, no new paid infrastructure of any kind.

## 17. Security scan

`git grep` over the tree for key/token/password/secret
patterns, Supabase URL shapes, JWT-shaped strings, and BEGIN
PRIVATE blocks: only placeholders (`<service-role-key>`,
`<project>`, `<password>`, `<ocr-space-key>`), test-only dummy
keys (`dummy-key-for-test`, never a real credential shape),
and documentation references. No `.env` tracked. Full output
in the report §15.

## 18. Known limitations / what was NOT done

- **No deployment executed**: no gcloud/docker/credentials in
  this environment (verified absent, not assumed). Status is
  PARTIAL by the mission's failure rule.
- No live Supabase touched; no OCR key configured (smoke =
  NOT CONFIGURED, honestly reported).
- Dependency versions resolve fresh at image build (no lock
  committed from this environment — pinning from a successful
  staging build is follow-up).
- `/docs` (Swagger UI) stays enabled on staging: schemas carry
  no secrets (asserted by test), and public docs aid staging
  verification; production exposure to be re-decided with the
  frontend.
- Frontend, RDKit, roles, AI, compare: untouched (non-goals).

## 19. Stage-19 gate

RDKit may begin after this stage: deployment procedure,
artifacts, and validation are complete; only execution against
real GCP/Supabase credentials remains, which is an operator
action, not a code gap.
