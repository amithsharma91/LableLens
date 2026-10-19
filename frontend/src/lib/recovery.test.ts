import { afterEach, describe, expect, it } from 'vitest';

import {
  MIN_PASSWORD_LENGTH,
  captureRecoveryLink,
  classifyAuthError,
  describeAuthError,
  scrubRecoveryUrl,
  validateNewPassword,
} from './recovery';

describe('captureRecoveryLink', () => {
  it('captures a PKCE code from the query string', () => {
    expect(captureRecoveryLink('?code=otp-123', '')).toEqual({
      kind: 'pkce',
      code: 'otp-123',
    });
  });

  it('captures implicit tokens from the fragment', () => {
    expect(
      captureRecoveryLink(
        '',
        '#access_token=at-1&refresh_token=rt-1&type=recovery',
      ),
    ).toEqual({
      kind: 'implicit',
      accessToken: 'at-1',
      refreshToken: 'rt-1',
    });
  });

  it('prefers the PKCE code when both are present', () => {
    expect(
      captureRecoveryLink('?code=otp-1', '#access_token=at-1').kind,
    ).toBe('pkce');
  });

  it('reports none when neither shape is present', () => {
    expect(captureRecoveryLink('', '')).toEqual({ kind: 'none' });
    expect(captureRecoveryLink('?next=%2F', '')).toEqual({ kind: 'none' });
    expect(captureRecoveryLink('', '#foo=bar')).toEqual({ kind: 'none' });
  });

  it('treats an empty code as no code', () => {
    expect(captureRecoveryLink('?code=', '')).toEqual({ kind: 'none' });
  });

  it('decodes percent-encoded values and survives malformed escapes', () => {
    expect(captureRecoveryLink('?code=a%2Db', '').code).toBe('a-b');
    expect(captureRecoveryLink('?code=%E0%A4%A', '')).toEqual({ kind: 'none' });
  });
});

describe('scrubRecoveryUrl', () => {
  afterEach(() => {
    window.history.replaceState(null, '', '/');
  });

  it('removes the query string and fragment from the address bar', () => {
    window.history.replaceState(
      null,
      '',
      '/auth/reset-password?code=otp-secret#access_token=at-secret',
    );
    scrubRecoveryUrl();
    expect(window.location.search).toBe('');
    expect(window.location.hash).toBe('');
    expect(window.location.pathname).toBe('/auth/reset-password');
  });
});

describe('classifyAuthError', () => {
  it('maps an expired OTP to the expired phase', () => {
    expect(classifyAuthError({ code: 'otp_expired' })).toBe('expired');
    expect(classifyAuthError({ code: 'access_token_expired' })).toBe('expired');
  });

  it('maps a null error to invalid', () => {
    expect(classifyAuthError(null)).toBe('invalid');
  });

  it('maps policy failures to the generic error phase', () => {
    for (const code of ['weak_password', 'same_password', 'over_email_send_rate_limit']) {
      expect(classifyAuthError({ code })).toBe('error');
    }
  });

  it('maps a rejected code exchange to invalid', () => {
    expect(classifyAuthError({ code: 'invalid_grant' })).toBe('invalid');
    expect(classifyAuthError({ code: 'bad_code_verifier' })).toBe('invalid');
  });

  it('maps validation failures to invalid', () => {
    expect(classifyAuthError({ code: 'validation_failed' })).toBe('invalid');
  });

  it('defaults unknown errors to error', () => {
    expect(classifyAuthError({ code: 'something_new' })).toBe('error');
    expect(classifyAuthError({})).toBe('error');
  });
});

describe('describeAuthError', () => {
  it('never includes a token', () => {
    const message = describeAuthError({
      code: 'weak_password',
      message: 'eyJhbGciOi.super.secret.token',
    });
    expect(message).not.toContain('eyJ');
    expect(message).toMatch(/too weak/i);
  });

  it('gives distinct advice for expiry', () => {
    expect(describeAuthError({ code: 'otp_expired' })).toMatch(/expired/i);
  });
});

describe('validateNewPassword', () => {
  it('accepts a long matching pair', () => {
    const password = 'correct horse battery';
    expect(validateNewPassword(password, password)).toBeNull();
  });

  it('rejects a short password', () => {
    expect(validateNewPassword('a'.repeat(MIN_PASSWORD_LENGTH - 1), 'a'.repeat(MIN_PASSWORD_LENGTH - 1))).toMatch(
      /at least/i,
    );
  });

  it('rejects a mismatch', () => {
    expect(validateNewPassword('correct horse battery', 'different horse')).toMatch(
      /do not match/i,
    );
  });
});