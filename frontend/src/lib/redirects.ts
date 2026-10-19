/**
 * Redirect allowlist.
 *
 * Recovery links may carry a `next` destination. Anything attacker-controlled
 * in a URL that arrives by email is an open-redirect vector, so destinations
 * are restricted to an explicit, closed set of internal routes. This module
 * is pure and is unit-tested directly.
 */

export const ALLOWED_REDIRECT_PATHS = [
  '/',
  '/auth/forgot-password',
  '/auth/reset-password',
] as const;

export const DEFAULT_REDIRECT = '/';

function isAllowedPath(path: string): boolean {
  return (ALLOWED_REDIRECT_PATHS as readonly string[]).includes(path);
}

/**
 * Return `next` only if it is an explicitly allowed internal destination.
 * Otherwise return `fallback`.
 *
 * Rejects: absolute URLs, protocol-relative URLs (`//evil.test`), backslash
 * variants that some browsers normalise to `//`, control characters, and any
 * path not on the allowlist.
 */
export function sanitizeNext(
  next: string | null | undefined,
  fallback: string = DEFAULT_REDIRECT,
): string {
  if (typeof next !== 'string') return fallback;

  const candidate = next.trim();
  if (candidate === '') return fallback;

  // Must be root-relative. This alone rejects 'https://evil.test' and '//evil.test'.
  if (!candidate.startsWith('/')) return fallback;
  // Belt and braces: '//' and '/\' are protocol-relative in browsers.
  if (candidate.startsWith('//') || candidate.startsWith('/\\')) {
    return fallback;
  }
  if (candidate.includes('\\')) return fallback;
  // Control characters can be used to smuggle a second header/URL.
  if (/[\u0000-\u001f\u007f]/.test(candidate)) return fallback;

  // Compare only the path portion; query/fragment on an allowed path is fine.
  const pathOnly = candidate.split('#')[0]?.split('?')[0] ?? '';
  if (!isAllowedPath(pathOnly)) return fallback;

  return candidate;
}

/**
 * Build the absolute redirect destination handed to Supabase for a reset email.
 *
 * The path is a constant, not caller input, so this cannot be steered to an
 * arbitrary origin. The origin is the page's own origin.
 */
export function buildResetRedirectUrl(origin: string): string {
  const base = origin.replace(/\/+$/, '');
  return `${base}/auth/reset-password`;
}