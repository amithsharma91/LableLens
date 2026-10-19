/**
 * Canonical public-key rules.
 *
 * Single source of truth for "is this key safe to put in a browser bundle?".
 * It is imported by BOTH:
 *
 *   - src/lib/config.ts   (runtime validator; runs in the browser)
 *   - scripts/check-bundle-secrets.mjs  (build-time guard; runs in Node)
 *
 * Sharing the predicate is deliberate: the guard and the validator must agree,
 * or a legitimate key fails the build while a privileged one still passes a
 * code review. `src/lib/bundle-guard.test.ts` asserts they agree.
 *
 * DESIGN RULE: this module is bundled into the client. It therefore must NOT
 * contain the literal name of any privileged role or key type — those literals
 * would land in dist/ and trip the very guard that reads this file.
 * Everything below is POSITIVE (prove the key is publishable) so that no
 * forbidden literal is needed.
 *
 * This module is plain ESM with a sibling .d.ts so it can be shared by
 * TypeScript and by a plain-Node build script without a build step.
 */

/** Public publishable-key prefix. Safe to name: it is the *allowed* form. */
export const PUBLISHABLE_PREFIX = 'sb_publishable_';

/** The only role a browser bundle may ever hold. */
export const BROWSER_ROLE = 'anon';

/** Decode one base64url segment to a UTF-8 string, or null. */
export function decodeBase64Url(segment) {
  try {
    const base64 = segment.replace(/-/g, '+').replace(/_/g, '/');
    const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4);
    const binary = atob(padded);
    // Re-decode as UTF-8 so non-ASCII claims do not throw.
    const bytes = Uint8Array.from(binary, (ch) => ch.charCodeAt(0));
    return new TextDecoder().decode(bytes);
  } catch {
    return null;
  }
}

/**
 * Parse a three-segment JWT's claims, or null if it is not parseable.
 * Returns the claims object; does not verify any signature.
 */
export function readJwtClaims(token) {
  const segments = token.split('.');
  if (segments.length !== 3) return null;
  const payload = segments[1];
  if (!payload) return null;
  const decoded = decodeBase64Url(payload);
  if (decoded === null) return null;
  try {
    const claims = JSON.parse(decoded);
    if (typeof claims !== 'object' || claims === null) return null;
    return claims;
  } catch {
    return null;
  }
}

/** The role claim of a JWT, or null when absent/unparseable. */
export function jwtRole(token) {
  const claims = readJwtClaims(token);
  if (claims === null) return null;
  const role = claims.role;
  return typeof role === 'string' ? role : null;
}

/**
 * True only when the value can be PROVEN to be browser-safe.
 *
 * Accepts:
 *   - the modern publishable prefix, or
 *   - a three-segment JWT whose `role` claim is exactly the browser role.
 *
 * Refuses everything else, including a privileged JWT (its role claim is not
 * the browser role) and any unparseable value. Positive allowlisting means an
 * unrecognised format is refused rather than waved through.
 */
export function isPublishableKey(key) {
  if (typeof key !== 'string') return false;
  if (key.startsWith(PUBLISHABLE_PREFIX)) return true;
  return jwtRole(key) === BROWSER_ROLE;
}
