/**
 * Regression tests for the build-time bundle secret guard.
 *
 * These cover the false-positive fix: a legitimate legacy anon JWT
 * (`role: "anon"`) MUST be accepted, because the browser cannot authenticate
 * without it, while a privileged JWT and any unrecognised JWT must still be
 * refused.
 *
 * EVERY VALUE HERE IS SYNTHETIC. No project key, credential, or real token is
 * used, referenced, or readable by this suite.
 *
 * The suite also asserts that the runtime validator (src/lib/config.ts) and
 * the guard agree, which is the reason the predicate lives in
 * shared/public-key-rules.js.
 */

import { execFileSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

import { classifyJwt, scanText } from '../../scripts/check-bundle-secrets.mjs';
import { isPublishableKey } from '../../shared/public-key-rules.js';
import { readPublicConfig } from './config';

const GUARD = resolve(__dirname, '../../scripts/check-bundle-secrets.mjs');

// ---------------------------------------------------------------------------
// Synthetic value builders (never real credentials)
// ---------------------------------------------------------------------------

function b64url(value: unknown): string {
  return Buffer.from(JSON.stringify(value)).toString('base64url');
}

/** An unsigned JWT-shaped string whose payload claims `role`. */
function jwtWithRole(role: unknown): string {
  return `${b64url({ alg: 'HS256', typ: 'JWT' })}.${b64url({
    iss: 'synthetic',
    role,
  })}.${'S'.repeat(43)}`;
}

const ANON_JWT = jwtWithRole('anon');
const PRIVILEGED_JWT = jwtWithRole('service' + '_role');
const MODERN_KEY = `sb${'_'}publishable_${'a'.repeat(40)}`;
const SECRET_KEY = `sb${'_'}secret_${'b'.repeat(40)}`;

/**
 * JWT-SHAPED (so the scanner matches it) but whose payload is base64url that
 * does not decode to JSON. Must fail closed.
 */
const MALFORMED_JWT = `${b64url({ alg: 'HS256' })}.aaaaaaaaaaaaaa.${'S'.repeat(43)}`;

/** Not JWT-shaped at all: not a credential, so the scanner ignores it. */
const NOT_A_JWT = 'plain-text-not-a-token';

/** JWT-shaped whose payload decodes to JSON with no role claim. */
const NO_ROLE_JWT = `${b64url({ alg: 'HS256' })}.${b64url({ iss: 'synthetic' })}.${'S'.repeat(43)}`;

// ---------------------------------------------------------------------------
// The shared predicate
// ---------------------------------------------------------------------------

describe('isPublishableKey', () => {
  it('accepts a legacy JWT with the browser role', () => {
    expect(isPublishableKey(ANON_JWT)).toBe(true);
  });

  it('accepts the modern publishable-key format', () => {
    expect(isPublishableKey(MODERN_KEY)).toBe(true);
  });

  it('rejects a JWT with a privileged role claim', () => {
    expect(isPublishableKey(PRIVILEGED_JWT)).toBe(false);
  });

  it('rejects a JWT with no role claim', () => {
    expect(isPublishableKey(NO_ROLE_JWT)).toBe(false);
  });

  it('ignores text that is not JWT-shaped', () => {
    expect(scanText(`window.__K="${NOT_A_JWT}";`)).toEqual([]);
  });

  it('rejects malformed and non-key values', () => {
    expect(isPublishableKey(MALFORMED_JWT)).toBe(false);
    expect(isPublishableKey('')).toBe(false);
    expect(isPublishableKey('not-a-key')).toBe(false);
    expect(isPublishableKey(null)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Guard classification
// ---------------------------------------------------------------------------

describe('guard classification', () => {
  it('accepts a legacy anon JWT', () => {
    expect(classifyJwt(ANON_JWT)).toBeNull();
  });

  it('accepts the modern publishable-key format', () => {
    expect(classifyJwt(MODERN_KEY)).toBeNull();
  });

  it('rejects a JWT with a privileged role claim', () => {
    expect(classifyJwt(PRIVILEGED_JWT)).toMatch(/non-browser role claim/i);
  });

  it('rejects an unrecognised or malformed JWT', () => {
    expect(classifyJwt(MALFORMED_JWT)).toMatch(/malformed/i);
    expect(classifyJwt(NO_ROLE_JWT)).toMatch(/malformed/i);
  });
});

describe('scanText', () => {
  it('allows a bundle containing the publishable anon JWT', () => {
    expect(scanText(`window.__K="${ANON_JWT}";`)).toEqual([]);
  });

  it('allows a bundle containing the modern publishable key', () => {
    expect(scanText(`window.__K="${MODERN_KEY}";`)).toEqual([]);
  });

  it('rejects a privileged JWT', () => {
    expect(scanText(`window.__K="${PRIVILEGED_JWT}";`)).toHaveLength(1);
  });

  it('rejects an sb_secret_ key', () => {
    expect(scanText(`window.__K="${SECRET_KEY}";`)).toHaveLength(1);
  });

  it('rejects a malformed JWT', () => {
    expect(scanText(`window.__K="${MALFORMED_JWT}";`)).toHaveLength(1);
  });

  it('rejects privileged names in plaintext', () => {
    expect(scanText('const k = "service' + '_role";')).toHaveLength(1);
    expect(scanText('process.env.SUPABASE_SERVICE' + '_ROLE')).toHaveLength(1);
  });

  it('flags a mixed bundle once per problem', () => {
    const findings = scanText(`${ANON_JWT} ${SECRET_KEY} ${PRIVILEGED_JWT}`);
    expect(findings).toHaveLength(2);
  });
});

// ---------------------------------------------------------------------------
// Runtime validator and guard must agree
// ---------------------------------------------------------------------------

describe('runtime validator agrees with the guard', () => {
  const CASES = [
    ANON_JWT,
    PRIVILEGED_JWT,
    MODERN_KEY,
    SECRET_KEY,
    NO_ROLE_JWT,
    MALFORMED_JWT,
  ];

  function runtimeAccepts(value: string): boolean {
    try {
      readPublicConfig({
        VITE_SUPABASE_URL: 'https://abcdefghijklmnop.supabase.co',
        VITE_SUPABASE_ANON_KEY: value,
      });
      return true;
    } catch {
      return false;
    }
  }

  it('accepts exactly what the guard accepts', () => {
    for (const value of CASES) {
      const guardAccepts = classifyJwt(value) === null;
      expect({
        label: value.slice(0, 12),
        guard: guardAccepts,
        runtime: runtimeAccepts(value),
      }).toEqual({
        label: value.slice(0, 12),
        guard: guardAccepts,
        runtime: guardAccepts,
      });
    }
  });
});

// ---------------------------------------------------------------------------
// End-to-end: the real guard binary, on synthetic bundles
// ---------------------------------------------------------------------------

function runGuard(bundleBody: string): { code: number; output: string } {
  const dir = join(process.cwd(), `.guard-test-tmp`);
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, 'app.js'), bundleBody, 'utf8');
  try {
    const output = execFileSync('node', [GUARD, dir], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    return { code: 0, output };
  } catch (error) {
    const err = error as { status?: number; stdout?: string; stderr?: string };
    return {
      code: err.status ?? 1,
      output: `${err.stdout ?? ''}${err.stderr ?? ''}`,
    };
  } finally {
    execFileSync('rm', ['-rf', dir], { stdio: 'ignore' });
  }
}

describe('guard end-to-end', () => {
  it('accepts a bundle containing a legacy anon JWT', () => {
    const { code, output } = runGuard(`window.__K="${ANON_JWT}";`);
    expect(code).toBe(0);
    expect(output).toContain('OK');
  });

  it('accepts a bundle containing the modern publishable key', () => {
    expect(runGuard(`window.__K="${MODERN_KEY}";`).code).toBe(0);
  });

  it('refuses a bundle containing a privileged JWT', () => {
    const { code, output } = runGuard(`window.__K="${PRIVILEGED_JWT}";`);
    expect(code).toBe(1);
    expect(output).toContain('BUILD REFUSED');
  });

  it('refuses a bundle containing an sb_secret_ key', () => {
    expect(runGuard(`window.__K="${SECRET_KEY}";`).code).toBe(1);
  });

  it('refuses a bundle containing a malformed JWT', () => {
    expect(runGuard(`window.__K="${MALFORMED_JWT}";`).code).toBe(1);
  });

  it('never echoes the offending value', () => {
    for (const secret of [PRIVILEGED_JWT, SECRET_KEY, MALFORMED_JWT]) {
      const { output } = runGuard(`window.__K="${secret}";`);
      expect(output).not.toContain(secret);
      // also not the bare token body
      expect(output).not.toContain(secret.split('.')[1]);
    }
  });
});
