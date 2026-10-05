# LabelLens — Stage-11 Authenticated API Boundary

**Date:** 2026-10-05  
**Branch:** `feat/label-pipeline-foundation`  
**Scope:** FastAPI boundary over Stages 2-10. V1–V7 untouched.
No frontend, OCR, RDKit, chemistry, roles, AI, providers, rules,
migrations, or deferred-FK activation.

## API architecture

Routes are adapters: HTTP in, validated service commands, domain
services, repositories. No chemistry, verification, evidence, or
review rules live in routes. Assembly happens in `create_app`
(factory with injected repos/verifier/registry/adapters); the
module-level app keeps prior imports working. A service-scope
middleware binds the service bundle to `request.state` per request
(Postgres: one connection + one transaction per request on the
serving event loop, so connections never cross loops and writes
commit atomically); request ID correlation travels alongside it.
No SQL appears in any API module (verified by review).

## Canonical-entity prerequisite

A decision's entity id comes from the *evidence* adapter, and
`claims.chemical_entity_id` references `chemical_entities`. The
service therefore checks that the entity is registered before writing
claims and fails with 422 `ENTITY_NOT_FOUND` instead of an opaque
integrity violation. Registering canonical entities is a service-role
import that has no route in this stage (deliberately: the API never
creates chemistry). The invariant is exercised, not bypassed: offline
tests seed the snapshot's entity ids explicitly, and the live test
registers them in the real table.

## Authentication

`Authorization: Bearer <token>` -> `Principal(subject, role)` via
the `TokenVerifier` interface. Missing/malformed/unknown/overlong
tokens and unconfigured verifiers all yield 401 with `WWW-Authenticate`
semantics implied by the envelope (no token oracle: identical
responses). Subjects match `[A-Za-z0-9_-]{1,64}` so they embed
safely in audit actor strings. Production path is Supabase JWT
verification (documented, not implemented -- no Supabase Auth
dependency exists yet); development/tests use an explicit static
map (`DEV_API_TOKENS`, never committed values).

## Authorization

Reads + observation creation/analysis: `authenticated`. Review
claim/decision: `reviewer` (403 otherwise). Service-role-only
operations (canonical writes) have no route at all. Reviewer
identity is `human:{subject}` derived server-side.

## Endpoint contract

See API_SPEC §100 for the route table. Notable behaviors:

- Create returns a collection (one observation per top-level
  parser node); raw text stored and returned verbatim.
- Optional client `observation_id` makes single-node creation
  idempotent; verification IDs are match-scoped (re-analysis of
  the same observation reuses rows; new observations get new rows).
- Analyze runs resolve + verify + persist + review routing and
  returns resolution, decision, stored IDs, and review ID (if
  routed). Nested children appear in response trees (deterministic
  re-parse); per-node persistence below top level is deferred.
- Verification responses separate decision, per-claim states,
  evidence with source names, and full decision history.
- Reviews list in Stage-9 priority order through bounded
  pagination (default 20, max 100). Decisions validate scope
  (identity-only, 422 otherwise), run re-verification, and persist
  transitions + new decisions. Stale evidence fails with 409.
  Persisted review events are replayed into the hydrated queue before
  any transition, so new audit events never reuse a positional event
  id (which would silently deduplicate the decision away).
- Errors use the spec envelope with spec codes; domain mapping is
  total (409 conflict/stale, 404 unknown, 403 forbidden, 422
  validation / `ENTITY_NOT_FOUND`, 500 generic without internals).

## Security assumptions

- Tokens are bearer secrets in transit (HTTPS assumed for any
  deployment; not enforced in code at this stage).
- Static token map is development-only; production requires the
  Supabase JWT verifier plus a secrets review.
- Service-role credential never leaves the backend (absent from
  responses, schemas, logs, errors, OpenAPI, and frontend config
  -- regression-tested).
- CORS stays environment-driven and restrictive (no wildcard);
  production origin still undeclared by design.
- Request bodies are size-bounded (raw 5000, reason 2000, refs
  bounded); unknown fields rejected (`extra="forbid"`); pagination
  capped; no PUT/DELETE routes exist.

## Deferred production items

Rate limiting (endpoints needing it: analyze, decision, observation
creation -- documented, not implemented), Supabase JWT verification,
per-user row scoping (no user_id yet), frontend origin declaration,
request log shipping. None are claimed done.
