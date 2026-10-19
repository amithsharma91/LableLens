import { describe, expect, it } from 'vitest';

import { ConfigError, isPublishableKey, readPublicConfig } from './config';

const VALID_URL = 'https://abcdefghijklmnop.supabase.co';
const VALID = {
  VITE_SUPABASE_URL: VALID_URL,
  VITE_SUPABASE_ANON_KEY: `sb${'_'}publishable_${'a'.repeat(32)}`,
};

/** Build an unsigned JWT-shaped string whose payload claims `role`. */
function jwtWithRole(role: string): string {
  const payload = btoa(JSON.stringify({ role, iss: 'supabase' }))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
  return `eyJhbGciOiJIUzI1NiJ9.${payload}.c2lnbmF0dXJl`;
}

describe('isPublishableKey', () => {
  it('accepts the modern publishable prefix', () => {
    expect(isPublishableKey(`sb${'_'}publishable_${'a'.repeat(32)}`)).toBe(true);
  });

  it('accepts a legacy JWT whose role claim is the browser role', () => {
    expect(isPublishableKey(jwtWithRole('anon'))).toBe(true);
  });

  it('refuses a legacy JWT with a privileged role claim', () => {
    expect(isPublishableKey(jwtWithRole('service' + '_role'))).toBe(false);
  });

  it('refuses an unparseable or wrong-shaped key', () => {
    expect(isPublishableKey('')).toBe(false);
    expect(isPublishableKey('not-a-key')).toBe(false);
    expect(isPublishableKey('eyJhbGciOiJIUzI1NiJ9.abc.def')).toBe(false);
  });
});

describe('readPublicConfig', () => {
  it('accepts a well-formed public configuration', () => {
    expect(readPublicConfig(VALID)).toEqual({
      supabaseUrl: VALID_URL,
      supabaseAnonKey: VALID.VITE_SUPABASE_ANON_KEY,
    });
  });

  it('rejects a missing URL', () => {
    expect(() =>
      readPublicConfig({ VITE_SUPABASE_ANON_KEY: VALID.VITE_SUPABASE_ANON_KEY }),
    ).toThrow(ConfigError);
  });

  it('rejects a missing anon key', () => {
    expect(() => readPublicConfig({ VITE_SUPABASE_URL: VALID_URL })).toThrow(
      ConfigError,
    );
  });

  it('rejects an empty or whitespace value', () => {
    expect(() =>
      readPublicConfig({ ...VALID, VITE_SUPABASE_URL: '   ' }),
    ).toThrow(ConfigError);
  });

  it('rejects a non-HTTPS or non-Supabase URL', () => {
    for (const bad of [
      'http://abcdefghijklmnop.supabase.co',
      'https://evil.test',
      'javascript:alert(1)',
      'https://abcdefghijklmnop.supabase.co.evil.test',
    ]) {
      expect(() => readPublicConfig({ ...VALID, VITE_SUPABASE_URL: bad })).toThrow(
        ConfigError,
      );
    }
  });

  it('refuses a privileged key and never echoes it', () => {
    const privileged = `sb${'_'}secret_${'x'.repeat(40)}`;
    let message = '';
    try {
      readPublicConfig({ ...VALID, VITE_SUPABASE_ANON_KEY: privileged });
    } catch (error) {
      message = (error as Error).message;
    }
    expect(message).toMatch(/not a publishable browser key/i);
    expect(message).not.toContain(privileged);
    expect(message).not.toContain('x'.repeat(40));
  });

  it('refuses a privileged JWT and never echoes it', () => {
    const privileged = jwtWithRole('service' + '_role');
    let message = '';
    try {
      readPublicConfig({ ...VALID, VITE_SUPABASE_ANON_KEY: privileged });
    } catch (error) {
      message = (error as Error).message;
    }
    expect(message).toMatch(/not a publishable browser key/i);
    expect(message).not.toContain(privileged);
  });

  it('accepts a real-shaped legacy anon JWT', () => {
    const legacy = jwtWithRole('anon');
    expect(readPublicConfig({ ...VALID, VITE_SUPABASE_ANON_KEY: legacy })).toEqual({
      supabaseUrl: VALID_URL,
      supabaseAnonKey: legacy,
    });
  });
});