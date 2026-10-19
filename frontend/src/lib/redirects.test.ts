import { describe, expect, it } from 'vitest';

import {
  ALLOWED_REDIRECT_PATHS,
  buildResetRedirectUrl,
  sanitizeNext,
} from './redirects';

describe('sanitizeNext', () => {
  it('accepts every explicitly allowed path', () => {
    for (const path of ALLOWED_REDIRECT_PATHS) {
      expect(sanitizeNext(path)).toBe(path);
    }
  });

  it('keeps an allowed path with a query string', () => {
    expect(sanitizeNext('/auth/reset-password?next=/')).toBe(
      '/auth/reset-password?next=/',
    );
  });

  it('falls back for absolute URLs', () => {
    for (const bad of [
      'https://evil.test/steal',
      'http://evil.test',
      'javascript:alert(1)',
    ]) {
      expect(sanitizeNext(bad)).toBe('/');
    }
  });

  it('falls back for protocol-relative and backslash variants', () => {
    for (const bad of ['//evil.test', '/\\evil.test', '/auth\\reset-password']) {
      expect(sanitizeNext(bad)).toBe('/');
    }
  });

  it('falls back for control characters', () => {
    expect(sanitizeNext('/auth/forgot-password\r\nX-Injected: 1')).toBe('/');
  });

  it('falls back for internal paths that are not on the allowlist', () => {
    for (const bad of ['/admin', '/auth', '/auth/reset-password/../admin']) {
      expect(sanitizeNext(bad)).toBe('/');
    }
  });

  it('falls back for empty, null and undefined input', () => {
    for (const bad of ['', '   ', null, undefined]) {
      expect(sanitizeNext(bad)).toBe('/');
    }
  });

  it('honours an explicit fallback', () => {
    expect(sanitizeNext('https://evil.test', '/auth/forgot-password')).toBe(
      '/auth/forgot-password',
    );
  });
});

describe('buildResetRedirectUrl', () => {
  it('builds an absolute URL on the given origin', () => {
    expect(buildResetRedirectUrl('http://localhost:3000')).toBe(
      'http://localhost:3000/auth/reset-password',
    );
  });

  it('does not double up slashes on a trailing slash origin', () => {
    expect(buildResetRedirectUrl('http://localhost:3000/')).toBe(
      'http://localhost:3000/auth/reset-password',
    );
  });
});