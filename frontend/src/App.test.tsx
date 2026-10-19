import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { App } from './App';

// ResetPasswordPage touches Supabase on mount. Routing assertions here are
// about routes; recovery behaviour is covered in RecoveryFlow.test.tsx, where
// the client is mocked.
vi.mock('./lib/supabase', () => ({
  getSupabase: () => ({
    auth: {
      exchangeCodeForSession: async () => ({ data: {}, error: null }),
      setSession: async () => ({ data: {}, error: null }),
      updateUser: async () => ({ data: {}, error: null }),
      signOut: async () => ({ error: null }),
      onAuthStateChange: () => ({ data: { subscription: { unsubscribe() {} } } }),
    },
  }),
  resetSupabaseForTests: () => undefined,
}));

afterEach(() => {
  window.history.replaceState(null, '', '/');
});

describe('routing', () => {
  it('renders the home route at /', () => {
    window.history.replaceState(null, '', '/');
    render(<App />);
    expect(
      screen.getByRole('heading', { name: 'LabelLens' }),
    ).toBeInTheDocument();
  });

  it('renders the reset request route', () => {
    window.history.replaceState(null, '', '/auth/forgot-password');
    render(<App />);
    expect(
      screen.getByRole('heading', { name: /reset your password/i }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
  });

  it('renders the recovery callback route', async () => {
    window.history.replaceState(null, '', '/auth/reset-password?code=otp-1');
    render(<App />);
    expect(
      await screen.findByRole('heading', { name: /choose a new password/i }),
    ).toBeInTheDocument();
  });

  it('renders a not-found page for an unknown route', () => {
    window.history.replaceState(null, '', '/nope');
    render(<App />);
    expect(
      screen.getByRole('heading', { name: /page not found/i }),
    ).toBeInTheDocument();
  });
});