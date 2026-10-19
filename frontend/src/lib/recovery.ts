/**
 * Recovery-link handling and the password-recovery state machine.
 *
 * WHY BOTH LINK FORMATS ARE SUPPORTED
 *
 * Supabase recovery links arrive in one of two shapes, and which one a given
 * project uses was NOT verified (it depends on the project's Auth settings):
 *
 *   PKCE      ?code=<otp>                    -> exchangeCodeForSession(code)
 *   implicit  #access_token=..&refresh_token=..&type=recovery
 *
 * Building for the wrong one produces a silently broken recovery link, so this
 * module handles both explicitly rather than assuming. Nothing here decides
 * which project setting is in force; it simply accepts either.
 *
 * URL SCRUBBING
 *
 * The code/token is read from the URL and the URL is stripped *before* any
 * network call. Leaving a recovery token in the address bar keeps it in
 * browser history and allows it to leak via the Referer header.
 *
 * This module is pure apart from `scrubRecoveryUrl`, which touches
 * window.history, and contains no Supabase dependency so it is unit-testable
 * without mocks.
 */

export type RecoveryPhase =
  | 'idle'
  | 'validating'
  | 'ready'
  | 'invalid'
  | 'expired'
  | 'submitting'
  | 'success'
  | 'error';

export type LinkKind = 'none' | 'pkce' | 'implicit';

export interface CapturedLink {
  kind: LinkKind;
  code?: string;
  accessToken?: string;
  refreshToken?: string;
}

export interface RecoveryState {
  phase: RecoveryPhase;
  /** Operator-facing text. Never contains a token or a full URL. */
  message?: string;
}

/** Minimum acceptable length for a new password. */
export const MIN_PASSWORD_LENGTH = 12;

function parseParams(raw: string): Record<string, string> {
  const out: Record<string, string> = {};
  const trimmed = raw.startsWith('?') || raw.startsWith('#') ? raw.slice(1) : raw;
  if (trimmed === '') return out;
  for (const pair of trimmed.split('&')) {
    if (pair === '') continue;
    const eq = pair.indexOf('=');
    const key = eq === -1 ? pair : pair.slice(0, eq);
    const value = eq === -1 ? '' : pair.slice(eq + 1);
    try {
      out[decodeURIComponent(key)] = decodeURIComponent(value);
    } catch {
      // A malformed percent-escape is not a usable parameter; ignore it.
    }
  }
  return out;
}

/**
 * Extract the recovery material from a URL's query and fragment.
 * Pure: no DOM access, so it is directly unit-testable.
 */
export function captureRecoveryLink(
  search: string,
  hash: string,
): CapturedLink {
  const query = parseParams(search);
  const fragment = parseParams(hash);

  const code = query['code'];
  if (typeof code === 'string' && code !== '') {
    return { kind: 'pkce', code };
  }

  const accessToken = fragment['access_token'];
  const refreshToken = fragment['refresh_token'];
  if (typeof accessToken === 'string' && accessToken !== '') {
    return {
      kind: 'implicit',
      accessToken,
      refreshToken: typeof refreshToken === 'string' ? refreshToken : undefined,
    };
  }

  return { kind: 'none' };
}

/**
 * Replace the current history entry with its path, dropping any query and
 * fragment. Safe to call outside a browser (no-op).
 */
export function scrubRecoveryUrl(): void {
  if (typeof window === 'undefined' || !window.history?.replaceState) return;
  const { pathname } = window.location;
  window.history.replaceState(null, '', pathname);
}

/**
 * Map a Supabase auth error onto a recovery phase.
 *
 * `otp_expired` gets its own phase because it needs different operator advice
 * from a malformed link: an expired link means "request a new one", while an
 * invalid link usually means "open the link in the same browser that requested
 * it".
 */
export function classifyAuthError(
  error: { code?: string; status?: number; message?: string } | null | undefined,
): RecoveryPhase {
  if (!error) return 'invalid';

  const code = (error.code ?? '').toLowerCase();

  if (code === 'otp_expired' || code === 'access_token_expired') {
    return 'expired';
  }
  if (code === 'weak_password') return 'error';
  if (code === 'same_password') return 'error';
  if (
    code === 'over_email_send_rate_limit' ||
    code === 'over_request_rate_limit' ||
    code === 'over_sms_send_rate_limit'
  ) {
    return 'error';
  }
  if (code === 'validation_failed' || code === 'invalid_credentials') {
    return 'invalid';
  }
  // A rejected code exchange means the link is bad, already used, or
  // replayed. That is an invalid link, not an unexpected server error, and
  // the operator advice differs ("request a new link").
  if (
    code === 'invalid_grant' ||
    code === 'bad_code_verifier' ||
    code === 'bad_json'
  ) {
    return 'invalid';
  }
  return 'error';
}

/** Human-readable, token-free explanation for a failed password update. */
export function describeAuthError(
  error: { code?: string; message?: string } | null | undefined,
): string {
  const code = (error?.code ?? '').toLowerCase();
  switch (code) {
    case 'weak_password':
      return 'That password is too weak. Choose a longer password.';
    case 'same_password':
      return 'The new password must be different from the current one.';
    case 'over_email_send_rate_limit':
    case 'over_request_rate_limit':
      return 'Too many attempts. Please wait a few minutes and try again.';
    case 'otp_expired':
    case 'access_token_expired':
      return 'This recovery link has expired. Request a new one.';
    default:
      return 'Something went wrong. Please request a new recovery link.';
  }
}

/**
 * Validate a new password. Returns an error message, or null when acceptable.
 * Client-side only; the server remains authoritative.
 */
export function validateNewPassword(
  password: string,
  confirmation: string,
): string | null {
  if (password.length < MIN_PASSWORD_LENGTH) {
    return `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`;
  }
  if (password !== confirmation) {
    return 'The two passwords do not match.';
  }
  return null;
}