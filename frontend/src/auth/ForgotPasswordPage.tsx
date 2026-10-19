import { useState, type FormEvent } from 'react';

import { getSupabase } from '../lib/supabase';
import { buildResetRedirectUrl } from '../lib/redirects';

type Status = 'idle' | 'sending' | 'sent' | 'error';

/**
 * The confirmation text is intentionally identical whether or not the address
 * has an account. Any difference would let an unauthenticated caller probe
 * which email addresses are registered.
 */
const NEUTRAL_SENT_MESSAGE =
  'If that address has an account, a password reset link is on its way. ' +
  'Check your inbox and your spam folder.';

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState<Status>('idle');

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatus('sending');
    try {
      const supabase = getSupabase();
      const { error } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: buildResetRedirectUrl(window.location.origin),
      });
      if (error) {
        // Even a rate-limit or delivery failure returns the neutral message:
        // reporting it differently would reintroduce account enumeration.
        setStatus('sent');
        return;
      }
      setStatus('sent');
    } catch {
      setStatus('sent');
    }
  }

  return (
    <main>
      <h1>Reset your password</h1>

      {status === 'sent' ? (
        <p role="status">{NEUTRAL_SENT_MESSAGE}</p>
      ) : (
        <form onSubmit={onSubmit} noValidate>
          <label htmlFor="email">Email address</label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <button type="submit" disabled={status === 'sending'}>
            {status === 'sending' ? 'Sending…' : 'Send reset link'}
          </button>
        </form>
      )}

      <p>
        <a href="/auth/reset-password">Already have a link?</a>
      </p>
    </main>
  );
}