# LabelLens Frontend — Account Recovery

Minimal React + TypeScript + Vite frontend providing the **password-recovery
flow only**. It is not the product UI.

Routes:

| Route | Purpose |
|---|---|
| `/` | Placeholder home |
| `/auth/forgot-password` | Request a password reset email |
| `/auth/reset-password` | Recovery callback + new-password form |

---

## Local setup

Requires Node `^22.12.0 || >=24.0.0` (verified on Node v22.23.3).

```bash
cd frontend
npm ci                 # reproducible: installs exactly what package-lock.json pins
cp .env.example .env.local
# edit .env.local and set the two VITE_ values
npm run dev            # http://localhost:3000
```

### Configuration

Only two variables may reach the browser:

```
VITE_SUPABASE_URL=https://<project-ref>.supabase.co
VITE_SUPABASE_ANON_KEY=<publishable anon key>
```

Get them from Supabase → Project Settings → API. The anon key is designed to
be visible in browsers.

**Never put the project's service-role key anywhere in this directory.** It
bypasses row-level security entirely. Three controls enforce this:

1. Vite only inlines `VITE_`-prefixed variables into the client bundle.
2. `src/lib/config.ts` positively verifies the key is publishable and refuses
   to start otherwise — including a privileged JWT whose role claim is not the
   browser role.
3. `npm run build` fails if the built bundle contains anything privileged.

The build-time guard (`scripts/check-bundle-secrets.mjs`) allows exactly two
things in the bundle — the modern publishable key, and a legacy JWT whose
`role` claim is `anon` — because the browser cannot authenticate without one.
It refuses a privileged JWT, an `sb_secret_` key, and any JWT whose payload
cannot be decoded or carries no role claim (fails closed). It never prints the
matched value.

The runtime validator (`src/lib/config.ts`) and the build guard share one
predicate (`shared/public-key-rules.js`), so they cannot disagree, and
`src/lib/bundle-guard.test.ts` asserts they agree.

`.env.local` is git-ignored. `.env.example` holds placeholders only.

---

## Opening the app on a phone

**`localhost` on a phone means the phone itself, not your development
machine.** A phone has no route to your laptop's `localhost`; on the phone,
`http://localhost:3000` points at the phone and nothing will be there.

To reach the dev server from a phone, use your machine's LAN address:

```bash
# find it, then open this on the phone (same Wi-Fi)
ip addr | grep 'inet '        # e.g. 192.168.1.42
# -> http://192.168.1.42:3000
```

That is a **different origin** from `http://localhost:3000`. Before recovery
will work from a phone you must, for that address:

1. Add the exact phone URL to Supabase → Authentication → URL Configuration →
   **Redirect URLs**.
2. Add that origin to the backend's `ALLOWED_ORIGINS`, or every request fails
   CORS.

Prefer verifying recovery on the development machine first; phone testing adds
two configuration changes and cannot be verified offline.

---

## Recovery flow behaviour

The recovery link format is **not assumed**. Supabase uses two shapes and which
one a project uses was not verified, so both are handled explicitly:

| Link shape | Handling |
|---|---|
| `?code=<otp>` (PKCE) | `auth.exchangeCodeForSession(code)` |
| `#access_token=…&refresh_token=…` (implicit) | `auth.setSession(...)` |

The URL is **scrubbed before any network call**, so the code/token does not
survive in browser history or leak via the `Referer` header.

States rendered: `validating`, `ready`, `invalid` (bad/used/replayed link),
`expired` (needs a new link), `submitting`, `success`, `error`.

Security behaviour:

- The reset-request confirmation is **identical whether or not the account
  exists**, so the page cannot be used to discover registered addresses.
- Post-reset `next` destinations are restricted to a closed allowlist of
  internal routes (`src/lib/redirects.ts`); absolute, protocol-relative and
  backslash URLs are rejected.
- The user is **signed out after a successful password change**, because a
  recovery session is a privileged session.
- Tokens are never logged and never rendered.

---

## Commands

| Command | Does |
|---|---|
| `npm run dev` | Dev server on port 3000, `strictPort` (a clash fails loudly) |
| `npm test` | Offline vitest suite; Supabase is mocked, no network |
| `npm run lint` | `tsc --noEmit` |
| `npm run build` | typecheck → `vite build` → bundle secret guard |
| `npm run check:secrets` | Bundle guard on its own |

`maxWorkers` is pinned to 1 in `vite.config.ts` for determinism; raise it on
machines with memory headroom.

---

## Not verified

- **No real email was sent** and **no live Supabase recovery was exercised.**
  Everything in this repo is tested offline with a mocked Supabase client.
- Which recovery-link format your project actually uses (PKCE vs implicit) is
  **unconfirmed** and needs checking in Supabase → Authentication → Providers.
  Both paths are implemented, but the flow has not been exercised end to end.
- Redirect URL and Site URL settings in the dashboard were not inspected or
  changed.
