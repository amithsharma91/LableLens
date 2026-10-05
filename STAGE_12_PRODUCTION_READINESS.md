# Stage 12 — Production Readiness

Date: 2026-10-05
Scope: real Supabase JWT verification (Part A), controlled canonical
entity registration/import (Part B), application rate limiting on
sensitive API operations (Part C), plus tests and documentation.

Verification rules V1–V7 are **unchanged**
(`VERIFICATION_RULES_VERSION = "1.0.0"`). No new verification rule, no
new chemistry source, and no chemistry calculation were introduced.

---

## 1. What this stage adds

| Part | Capability | Entry point |
|---|---|---|
| A | Supabase access-token verification against the project JWKS | `app/api/supabase_jwt.py`, `app/api/jwks.py`, `app/api/auth.py` |
| B | Canonical entity registration from the approved snapshot | `app/services/registration.py`, `app/cli/import_canonical_entities.py` |
| C | Rate limiting on the three sensitive write operations | `app/services/rate_limit.py`, `app/api/limits.py` |

Nothing in this stage is reachable from a new HTTP route. Part A
replaces the identity implementation behind the existing
`TokenVerifier` interface; Part B is an administrative CLI; Part C is a
FastAPI dependency on routes that already existed.

---

## 2. Part A — Supabase JWT verification

### 2.1 What is verified

For every token presented as `Authorization: Bearer <token>`, the
production verifier:

1. reads the JOSE header and requires `kid` and `alg`;
2. selects the public key from the project JWKS document
   (`<SUPABASE_URL>/auth/v1/.well-known/jwks.json`, per
   <https://supabase.com/docs/guides/auth/jwts> and
   <https://supabase.com/docs/guides/auth/signing-keys>);
3. binds the key to the algorithm (`PyJWK(entry, algorithm=alg)`) so a
   key published for one algorithm cannot verify a token signed with
   another;
4. **verifies the signature** — there is no decode-without-verify path
   anywhere in the codebase;
5. verifies `iss`, `aud`, `exp`, `nbf`, `iat` and the subject, with
   `exp`/`iss`/`sub` required;
6. rejects any token whose `role` claim is a database role rather than
   a person (`service_role`, `service_role_backend`, `supabase_admin`,
   `supabase_auth_admin`, `supabase_storage_admin`, `postgres`, `anon`,
   `authenticated_api`).

Consequences that matter:

* The backend's own service-role credential can never act as a user.
  It fails authentication (401) instead of acquiring a subject.
* Reviewer authority comes **only** from the operator allowlist
  `SUPABASE_REVIEWER_SUBJECTS`. A user cannot grant themselves review
  rights by putting a claim in their own token (`user_metadata`,
  `app_metadata`, custom claims) — those claims are never read.

### 2.2 JWKS caching and key rotation

`app/api/jwks.py` holds a bounded `JWKSCache`:

* HTTPS only — a non-HTTPS JWKS URL is refused at construction;
* TTL-bounded (`SUPABASE_JWT_JWKS_TTL_SECONDS`, default 300 s, below
  the 10-minute edge cache Supabase documents);
* unknown `kid` forces at most one fetch per
  `SUPABASE_JWT_JWKS_MIN_REFRESH_SECONDS` (default 30 s), so a flood of
  tokens with bogus key ids cannot turn into a fetch flood — this also
  covers *failed* fetches;
* the key set is bounded (`SUPABASE_JWT_JWKS_MAX_KEYS`, default 16) and
  the response size is bounded (64 KB); an oversized or unusable
  document is refused rather than trusted;
* the key is returned as a `cryptography` public key object, and a
  single lock serialises refreshes.

Rotation behaviour (verified in tests): Supabase publishes a new key →
a token signed by it verifies after at most one refresh; the retired
key keeps working only until the cache TTL expires, which is the
documented grace window and is bounded by cache lifetime rather than by
anything a caller controls. After TTL expiry the retired key is
refused.

### 2.3 Failure behaviour (fail closed)

`build_token_verifier()` raises `RuntimeError` — refusing to construct
the application — when:

* `ENVIRONMENT=production` and Supabase verification is not configured
  (no issuer/JWKS);
* `ENVIRONMENT=production` and `DEV_API_TOKENS` is set (static tokens
  are impossible in production; there is no silent fallback);
* `ENVIRONMENT=production` and no algorithm is configured.

Additional closed doors:

* JWKS unreachable, unknown `kid`, malformed token, expired/not-yet-valid
  token, wrong issuer, wrong audience, unsupported algorithm, missing
  `sub`, bad subject charset → all produce the **same** public
  `401 UNAUTHORIZED` with the message `authentication required` and an
  empty details object. The internal reason is logged (category only,
  never token material) so operators can debug without giving a caller
  an oracle. A test asserts all failure categories produce
  byte-identical public responses.
* Symmetric (HS256) projects fail closed: Supabase publishes no keys
  for symmetric projects and documents shared-secret verification as
  not recommended, so no algorithm is configured that could verify
  them.
* Oversized tokens (> 4096 characters) are rejected before parsing.

### 2.4 The principal carries only trusted material

`Principal` holds `subject`, `role`, `verifier`, `token_id` (`kid`),
`issuer`, `expires_at`, and the derived reviewer id
`human:{subject}`. Email, phone, or any other client-controlled claim
is never copied into it, so it cannot reach a database row or a log
line by accident. No token or claim is ever returned in a response body
or persisted; tests assert both.

### 2.5 Configuration (all from the environment)

| Variable | Default | Meaning |
|---|---|---|
| `SUPABASE_URL` | — | Project URL; issuer and JWKS are derived from it |
| `SUPABASE_JWT_ISSUER` | derived | `<SUPABASE_URL>/auth/v1` |
| `SUPABASE_JWT_JWKS_URL` | derived | `<issuer>/.well-known/jwks.json` |
| `SUPABASE_JWT_AUDIENCE` | `authenticated` | Comma-separated accepted `aud`; `*` disables the audience check explicitly (never the default) |
| `SUPABASE_JWT_ALGORITHMS` | `ES256,RS256` | Asymmetric only |
| `SUPABASE_JWT_LEEWAY_SECONDS` | `60` | Clock-skew tolerance |
| `SUPABASE_JWT_JWKS_TTL_SECONDS` | `300` | Key-set cache TTL |
| `SUPABASE_JWT_JWKS_MIN_REFRESH_SECONDS` | `30` | Floor between forced refreshes |
| `SUPABASE_JWT_JWKS_MAX_KEYS` | `16` | Bound on cached keys |
| `SUPABASE_JWT_FETCH_TIMEOUT_SECONDS` | `5.0` | JWKS fetch timeout |
| `SUPABASE_REVIEWER_SUBJECTS` | — | Comma-separated reviewer subject allowlist |

Nothing is hard-coded and no secret is needed: public keys are fetched
from the project's own JWKS endpoint. Signing keys are never configured
in this service.

---

## 3. Part B — Canonical entity registration and import

### 3.1 One authoritative path

`app/cli/import_canonical_entities.py` is the only registration entry
point:

```bash
DATABASE_URL=postgresql+asyncpg://… ENTITY_IMPORT_CONFIRM=service-role \
    python -m app.cli.import_canonical_entities \
    --expect-snapshot-version canonical_v1
```

* There is **no HTTP route**, no admin endpoint, and no request body
  that can create an entity. The API still never creates chemistry.
* The interlock is explicit: without `ENTITY_IMPORT_CONFIRM=service-role`
  the command refuses and exits 1 before touching the database.
* It requires direct database credentials (the service role); the API
  process never holds this variable.

### 3.2 What may be registered

Only **approved canonical records** from a versioned snapshot:

* the artifact's `verification_rule_version` must equal the frozen
  gate version `1.0.0`;
* `--expect-snapshot-version` (when given) must match the artifact;
* every record must be `verification_status = verified`; `provisional`,
  `conflicted`, `unknown` and `unverified` records are refused;
* `entity_type` and `representation_type` must be in the existing
  approved vocabulary (a salt stays a salt, a mixture stays a mixture —
  no reclassification);
* provenance must be complete: `source_id`, `record_locator`,
  `retrieved_at`, `source_class`, `license_note`;
* `preferred_name`, `verified_at`, and at least one identity identifier
  must be present, and identifier values must be well-formed for their
  type (e.g. `pubchem_cid` must be numeric);
* duplicate entity ids inside one artifact are refused.

Validation runs over the **whole** artifact before any write. If a
single record is unacceptable, the run raises `RegistrationRejected`
carrying a deterministic report of every rejection reason, and nothing
is written — not the valid records, not the aliases.

### 3.3 Determinism, idempotency, atomicity

* Entity identity is stable: a UUID id is kept verbatim; any other
  stable id maps to `uuid5("canonical-entity:<id>")`. Alias ids are
  `uuid5`-derived. Re-running the import cannot create a second
  identity.
* Entity rows are written with `ON CONFLICT DO NOTHING`, so a repeated
  run reports the records as already present and creates no duplicates
  (verified on live Postgres: 4 registered → 4 already present, row
  counts unchanged).
* The run is all-or-nothing: entity and alias writes share one
  transaction. An injected mid-import write failure rolls the whole
  import back (verified against live Postgres: zero rows survive).
* The report is deterministic JSON with no timestamps: same artifact in,
  same report out.

Observed CLI behaviour on a fresh database (migrations 001–003 applied):

```
$ python -m app.cli.import_canonical_entities            # no confirmation
refused: set ENTITY_IMPORT_CONFIRM=service-role …        exit 1

$ … ENTITY_IMPORT_CONFIRM=service-role …                  exit 0
{"records_already_present": 0, "records_considered": 4,
 "records_registered": 4, "records_rejected": 0, …}

$ … ENTITY_IMPORT_CONFIRM=service-role …                  exit 0
{"records_already_present": 4, "records_considered": 4,
 "records_registered": 0, "records_rejected": 0, …}
```

A tampered artifact (one record marked `provisional`) exits 1 with the
rejection reason and leaves the row count unchanged.

### 3.4 Provenance

Each registered row carries a `metadata` JSONB document with:

```json
{
  "snapshot_version": "canonical_v1",
  "rules_version": "1.0.0",
  "verification_status": "verified",
  "verified_at": "…",
  "imported_by": "canonical-registration-import",
  "provenance": {"source_id": "PUBCHEM", "record_locator": "https://…",
                 "retrieved_at": "…", "source_class": "A",
                 "license_note": "…", "source_version": "…"},
  "identifiers": [{"id_type": "pubchem_cid", "value": "311",
                   "provenance_note": "…"}, …]
}
```

Values are transcribed verbatim from the approved artifact — no
descriptor is computed, no weight is derived, nothing is inferred. A
field absent from the source is stored as `NULL` (tested).

### 3.5 Registry integration (one projection point)

The resolver registry is built from the registered rows only:

```python
build_registry(entity_rows, alias_rows) -> InMemoryRegistry
```

* `main.py` loads `chemical_entities` + `ingredient_aliases` at startup
  and hands the projection to the request factory. If that load fails,
  the registry stays **empty** (candidates unresolved) rather than
  partially populated — the safe failure direction.
* A live provider response is never injected into the registry, so a
  lookup can only return an entity that went through the import.
* `RegistryEntry.ref` stays registry-local (`CANON-<12 hex>`), never
  the entity UUID — the Stage-5 invariant is preserved; the API's
  `candidate_ref` values in the flow test are `CANON-…`.
* Identifiers come from `metadata.identifiers`; `entity_class` comes
  from the approved `representation_type`.
* Re-running the import is visible to the resolver only after an
  application restart (no reload endpoint exists). This is stated
  rather than hidden.

---

## 4. Part C — Application rate limiting

### 4.1 Limited operations (exactly three)

| Action | Route | Default budget |
|---|---|---|
| `observations.create` | `POST /api/v1/observations` | 30 / 60 s |
| `observations.analyze` | `POST /api/v1/observations/{id}/analyze` | 20 / 60 s |
| `reviews.decision` | `POST /api/v1/reviews/{id}/decision` | 20 / 60 s |

Reads (`GET`, health, health/dependencies) are deliberately **not**
limited. `POST /api/v1/reviews/{id}/claim` is also not limited: it is
identity-bound, cheap, and reviewer-scoped.

### 4.2 Design

* `RateLimiter` is a one-method protocol (`hit(key, limit,
  window_seconds) -> RateLimitDecision`), so the backend can become
  Redis or database-backed without touching routes or domain code.
  Only `InMemoryRateLimiter` ships in this stage.
* Identity is the **authenticated principal**: the bucket key is
  `"<action>|<verified subject>"`. No header (`X-User-ID`,
  `X-Reviewer-ID`, …) and no body field can influence it — request
  schemas forbid unknown fields, and a test asserts a payload cannot
  bypass or redirect a bucket. `RATE_LIMIT_INCLUDE_IP` (default
  `false`) can add the peer address as a second dimension; it is off by
  default because behind a proxy the peer address is the proxy's.
* Windows are fixed, lazily expired, and computed from an injectable
  clock, so behaviour is deterministic in tests (no sleeps).
* Storage is bounded: at most `RATE_LIMIT_MAX_KEYS` (default 10 000)
  buckets are tracked and the least-recently-used one is evicted beyond
  that. A bounded limiter degrades accuracy, never correctness.
* The review-decision route passes `require_reviewer` into the
  limiter dependency, so the stricter role check runs **before** any
  bucket is consumed.

### 4.3 Responses

```json
HTTP/1.1 429 Too Many Requests
Retry-After: 60
{"error": {"code": "RATE_LIMITED", "message": "too many requests",
           "details": {"retry_after_seconds": 60,
                       "action": "observations.create"}},
 "meta": {"request_id": "…", "api_version": "v1"}}
```

`Retry-After` is emitted by the single `ApiError` handler from
`request.state.rate_limit_retry_after`, so every 429 looks the same.
No bucket internals, subjects, or counters are disclosed.

### 4.4 Fail-safe (fail closed)

If the limiter backend raises, the request is refused with
`503 RATE_LIMITER_UNAVAILABLE` (message: `request could not be
admitted; retry shortly`) and the sensitive write does not happen.
Degrading to "allow" would silently disable the abuse control exactly
when the backend is unhealthy.

### 4.5 Configuration

| Variable | Default | Meaning |
|---|---|---|
| `RATE_LIMIT_ENABLED` | `true` | Master switch (`false`/`0`/`off`/`no` disables) |
| `RATE_LIMIT_OBSERVATION_CREATE` | `30/60` | `count/window_seconds` |
| `RATE_LIMIT_ANALYZE` | `20/60` | `count/window_seconds` |
| `RATE_LIMIT_REVIEW_DECISION` | `20/60` | `count/window_seconds` |
| `RATE_LIMIT_INCLUDE_IP` | `false` | Also key by peer address |
| `RATE_LIMIT_MAX_KEYS` | `10000` | Bound on tracked buckets |

A policy of `0/0` (or an unparsable value) means "not configured" for
that action, and no bucket is consumed. Routes carry no numbers.

### 4.6 Known limitation — single process

The in-memory limiter is per process. It protects one API instance and
is **not** distributed protection: running N replicas multiplies the
effective limit by N, and a restart clears all buckets. This is
documented in the module docstring, in `SECURITY.md`, and asserted by
tests (state lives in one process; a custom backend only needs the
one-method protocol). Moving to a shared backend is a configuration and
deployment task, not a code rewrite.

---

## 5. Development vs production configuration

| Concern | Development / tests | Production |
|---|---|---|
| Identity | `DEV_API_TOKENS` static map (`token:subject:role`) **or** Supabase JWT when configured | Supabase JWT only; `DEV_API_TOKENS` set → application refuses to build |
| Missing auth config | App builds, data routes answer `401` (no verifier) | App refuses to build |
| Reviewer role | Token map role, or `SUPABASE_REVIEWER_SUBJECTS` allowlist | `SUPABASE_REVIEWER_SUBJECTS` allowlist only |
| Rate limits | Configured defaults apply; tests inject their own limiter/policy | Configured defaults apply |
| Entity registration | CLI with `ENTITY_IMPORT_CONFIRM=service-role` | Same CLI; the API process never sets it |

When Supabase verification is configured in development, it wins and
the static token map is ignored (with a warning log), so a
misconfiguration cannot silently downgrade the boundary.

---

## 6. Verification performed

Commands run from `backend/` with the project virtualenv:

| Check | Result |
|---|---|
| `flake8 app --max-line-length=88` | clean |
| `python -m compileall -q app` | clean |
| `pytest app/tests` (no database) | **406 passed, 38 skipped** |
| `pytest app/tests` (live Postgres via `TEST_DATABASE_URL`) | **444 passed** |
| Import on a fresh database (migrations 001–003 applied) | 4 registered; second run 4 already present; tampered artifact refused with no writes |
| `git diff --check` | see the Stage-12 report |

New tests added by this stage (155 total):

| File | Tests | Covers |
|---|---|---|
| `app/tests/unit/test_supabase_jwt.py` | 35 | valid/invalid tokens, expiry + leeway, `nbf`, wrong issuer/audience, unsupported algorithm, malformed, missing `sub`, unknown/missing `kid`, key rotation + grace window, refresh cooldown, bounded key set, oversized key set, non-HTTPS refusal, unreachable keys, signing-only keys, production fail-closed configuration |
| `app/tests/unit/test_rate_limit.py` | 24 | policy parsing, fixed-window behaviour, window reset, partial expiry, backwards clock, subject/action isolation, key-shaping hostility, bounded storage, eviction, reset, unlimited decision |
| `app/tests/unit/test_registration.py` | 36 | approved artifact import, deterministic report, field-by-field transcription, idempotency, stable identity, refusal matrix (provenance, status, entity type, identifiers, name, date, duplicate ids), parser-level refusals, version checks, rollback, salt/mixture preservation, no inference, provenance persistence, aliases, registry projection, "no other table touched" |
| `app/tests/api/test_api_supabase_auth.py` | 18 | HTTP path end-to-end with a mocked JWKS transport: valid token accepted, reviewer subject reaches reviewer routes, non-reviewer 403, identical 401 for every failure category, service-role/anon tokens rejected, rotation after refresh, headers cannot override identity, spoofed body fields rejected (422), no token in response/logs/store, production app refuses missing Supabase config or static tokens |
| `app/tests/api/test_api_rate_limit.py` | 17 | 429 + `Retry-After` + envelope, per-subject and per-action isolation, payload cannot bypass, unauthenticated requests are not limited (401), bucket key derivation, reads never limited, master switch, limiter failure → 503, backend-agnostic protocol, configuration-driven defaults |
| `app/tests/integration/test_registration_postgres.py` | 18 | live import, provenance columns, salt preservation, aliases, idempotency, identity stability, six refusal paths with zero rows written, real transaction rollback, registry projection from live rows, claim foreign key satisfiable, no other table touched |
| `app/tests/integration/test_production_flow.py` | 7 | JWT → principal → create → analyze → registry resolution → evidence → V1–V7 (all seven rules PASS) → persisted decision/claims/match rows; unregistered names resolve nothing; reviewer claim + decision with `human:{subject}` then 429; repeated creates → 429 with no row written; reads unlimited; unverified/privileged/garbage tokens never reach a route; snapshot artifact unmodified |

Keys are generated in-process per test (`cryptography` + real PyJWT
signing); the JWKS endpoint is an `httpx.MockTransport`. No real
Supabase project, no real key, and no committed credential is involved.
Test-only keys are ephemeral and never grant access to anything.

---

## 7. Explicitly not done (boundaries held)

* V1–V7 verification rules: unchanged (`1.0.0`).
* No RDKit, no molecular calculation, no descriptors, no structure
  generation, no formula inference.
* No AI/ML anywhere in the decision path.
* No frontend work.
* No role/permission taxonomy or role classification of ingredients.
* No new official chemistry providers; PubChem/ChEBI adapters are as
  delivered in Stage 8.
* No bulk auto-verification of arbitrary entities.
* No arbitrary user-created entities; only approved snapshot records
  can be registered, and only through the service-role import.
* No public entity-registration or import endpoint.
* No service-role key or credential handling inside the API process.
* No deferred foreign keys activated (`claims.chemical_entity_id`
  stays nullable at the database level; the service enforces
  registration before writing).
* No RLS enabled on `chemical_entities` / `ingredient_aliases` (they
  remain service-role only, an acknowledged Stage-13 candidate).
* No new database tables and no new migration: `chemical_entities`
  already had `metadata`, `first_verified_at`, and `last_verified_at`,
  which is where provenance and verification timestamps are stored.

---

## 8. Limitations and deferred work

1. **Rate limiting is per process.** Multiple replicas multiply the
   budget; a shared backend (Redis) is the next step.
2. **No RLS on the canonical entity tables.** Access control is
   application-level plus service-role credentials only.
3. **Registry freshness.** A re-run of the import requires an
   application restart to reach the resolver. No reload endpoint exists
   by design.
4. **Per-user row scoping** for user-owned data (scans, images,
   corrections) does not exist yet, because those tables do not exist
   yet.
5. **JWKS availability is on the request path.** If the key set cannot
   be fetched and no cached copy is usable, authentication fails closed
   (401/503 at startup) rather than accepting unverified tokens.
6. **Symmetric Supabase projects are unsupported** by design (no
   published keys, shared secrets not recommended by Supabase).
7. **No security headers middleware, no WAF/edge limiting, no audit
   sink** — the API returns the spec envelope and request IDs only.
8. **Testing uses a mocked JWKS transport.** The code path is real, but
   it has never been run against a live Supabase project; that requires
   a real project and is the first thing to verify on deployment.

---

## 9. Related documents

* `DECISIONS.md` — ADR-025 (JWT verification), ADR-026 (registration as
  a service-role import), ADR-027 (application rate limiting)
* `API_SPEC.md` §101 — Stage-12 implemented boundary
* `SECURITY.md` §4.1/§7 — production authentication boundary and the
  implemented rate limiter
* `DATABASE_SCHEMA.md` §14 — canonical entity registration, provenance
  storage, registry projection
* `CHANGELOG.md` — Stage 12 entry
* `STAGE_11_API.md` — the API boundary this stage hardens