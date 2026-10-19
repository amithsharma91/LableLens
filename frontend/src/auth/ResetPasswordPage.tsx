import { useEffect, useState, type FormEvent } from 'react';

import { getSupabase } from '../lib/supabase';
import { sanitizeNext } from '../lib/redirects';
import {
  captureRecoveryLink,
  classifyAuthError,
  describeAuthError,
  scrubRecoveryUrl,
  validateNewPassword,
  type RecoveryState,
} from '../lib/recovery';

const INITIAL: RecoveryState = { phase: 'idle' };

/**
 * Establish a recovery session from whatever the URL carried.
 *
 * Supports both Supabase recovery-link formats (see lib/recovery.ts) and
 * scrubs the URL before any network call.
 */
async function establishRecoverySession(): Promise<RecoveryState> {
  const captured = captureRecoveryLink(
    window.location.search,
    window.location.hash,
  );

  // Scrub first: the code/token must not survive in history or leak via Referer.
  scrubRecoveryUrl();

  if (captured.kind === 'none') {
    return {
      phase: 'invalid',
      message:
        'This page needs a recovery link. Open the link from your email, or request a new one.',
    };
  }

  const supabase = getSupabase();

  try {
    if (captured.kind === 'pkce' && captured.code) {
      const { error } = await supabase.auth.exchangeCodeForSession(
        captured.code,
      );
      if (error) {
        return { phase: classifyAuthError(error), message: describeAuthError(error) };
      }
    } else if (captured.accessToken && captured.refreshToken) {
      const { error } = await supabase.auth.setSession({
        access_token: captured.accessToken,
        refresh_token: captured.refreshToken,
      });
      if (error) {
        return { phase: classifyAuthError(error), message: describeAuthError(error) };
      }
    } else {
      return {
        phase: 'invalid',
        message: 'This recovery link is incomplete. Request a new one.',
      };
    }
  } catch {
    return {
      phase: 'error',
      message: 'Could not validate this recovery link. Request a new one.',
    };
  }

  return { phase: 'ready' };
}

export function ResetPasswordPage() {
  const [state, setState] = useState<RecoveryState>(INITIAL);
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');

  useEffect(() => {
    let cancelled = false;
    setState({ phase: 'validating' });
    void establishRecoverySession().then((next) => {
      if (!cancelled) setState(next);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const invalid = validateNewPassword(password, confirmation);
    if (invalid) {
      setState({ phase: 'error', message: invalid });
      return;
    }

    setState({ phase: 'submitting' });
    const supabase = getSupabase();
    const { error } = await supabase.auth.updateUser({ password });
    if (error) {
      setState({ phase: classifyAuthError(error), message: describeAuthError(error) });
      return;
    }

    // A recovery session is a privileged session. Do not leave it live after
    // the password has been changed.
    await supabase.auth.signOut().catch(() => undefined);

    const next = sanitizeNext(new URLSearchParams(window.location.search).get('next'));
    window.history.replaceState(null, '', next);
    setState({ phase: 'success' });
  }

  return (
    <main>
      <h1>Choose a new password</h1>

      {state.phase === 'validating' && (
        <p role="status">Validating your recovery link…</p>
      )}

      {state.phase === 'invalid' && (
        <section role="alert">
          <h2>Link not valid</h2>
          <p>{state.message}</p>
          <a href="/auth/forgot-password">Request a new link</a>
        </section>
      )}

      {state.phase === 'expired' && (
        <section role="alert">
          <h2>Link expired</h2>
          <p>{state.message}</p>
          <a href="/auth/forgot-password">Request a new link</a>
        </section>
      )}

      {state.phase === 'ready' && (
        <form onSubmit={onSubmit} noValidate>
          <label htmlFor="password">New password</label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />

          <label htmlFor="confirmation">Confirm new password</label>
          <input
            id="confirmation"
            name="confirmation"
            type="password"
            autoComplete="new-password"
            value={confirmation}
            onChange={(event) => setConfirmation(event.target.value)}
          />

          <button type="submit">Update password</button>
        </form>
      )}

      {state.phase === 'submitting' && <p role="status">Updating…</p>}

      {state.phase === 'error' && (
        <p role="alert">{state.message}</p>
      )}

      {state.phase === 'success' && (
        <section role="status">
          <h2>Password updated</h2>
          <p>You can now sign in with your new password.</p>
          <a href="/auth/forgot-password">Back</a>
        </section>
      )}
    </main>
  );
}