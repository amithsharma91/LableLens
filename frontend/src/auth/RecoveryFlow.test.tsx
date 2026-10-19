import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ForgotPasswordPage } from './ForgotPasswordPage';
import { ResetPasswordPage } from './ResetPasswordPage';

const exchangeCodeForSession = vi.fn();
const setSession = vi.fn();
const updateUser = vi.fn();
const signOut = vi.fn();
const resetPasswordForEmail = vi.fn();

vi.mock('../lib/supabase', () => ({
  getSupabase: () => ({
    auth: {
      exchangeCodeForSession,
      setSession,
      updateUser,
      signOut,
      resetPasswordForEmail,
      onAuthStateChange: () => ({
        data: { subscription: { unsubscribe() {} } },
      }),
    },
  }),
  resetSupabaseForTests: () => undefined,
}));

function renderAt(path: string, element: React.ReactElement) {
  window.history.replaceState(null, '', path);
  return render(<MemoryRouter>{element}</MemoryRouter>);
}

beforeEach(() => {
  exchangeCodeForSession.mockReset().mockResolvedValue({ data: {}, error: null });
  setSession.mockReset().mockResolvedValue({ data: {}, error: null });
  updateUser.mockReset().mockResolvedValue({ data: {}, error: null });
  signOut.mockReset().mockResolvedValue({ error: null });
  resetPasswordForEmail.mockReset().mockResolvedValue({ data: {}, error: null });
});

afterEach(() => {
  window.history.replaceState(null, '', '/');
});

describe('ForgotPasswordPage', () => {
  it('sends a reset request to an allowlisted destination', async () => {
    renderAt('/auth/forgot-password', <ForgotPasswordPage />);
    await userEvent.type(screen.getByLabelText(/email address/i), 'a@b.test');
    await userEvent.click(screen.getByRole('button', { name: /send reset link/i }));

    await waitFor(() => expect(resetPasswordForEmail).toHaveBeenCalledTimes(1));
    const call = resetPasswordForEmail.mock.calls[0];
    expect(call).toBeDefined();
    const [emailArg, options] = call ?? [];
    expect(emailArg).toBe('a@b.test');
    expect(options).toMatchObject({
      redirectTo: expect.stringMatching(/\/auth\/reset-password$/),
    });
  });

  it('confirms a known-good address neutrally', async () => {
    renderAt('/auth/forgot-password', <ForgotPasswordPage />);
    await userEvent.type(screen.getByLabelText(/email address/i), 'a@b.test');
    await userEvent.click(screen.getByRole('button', { name: /send reset link/i }));
    expect(await screen.findByRole('status')).toHaveTextContent(
      /if that address has an account/i,
    );
  });

  it('confirms an unknown address with the identical message', async () => {
    resetPasswordForEmail.mockResolvedValue({
      data: {},
      error: { message: 'User not found', code: 'user_not_found' },
    });
    renderAt('/auth/forgot-password', <ForgotPasswordPage />);
    await userEvent.type(screen.getByLabelText(/email address/i), 'nobody@nowhere.test');
    await userEvent.click(screen.getByRole('button', { name: /send reset link/i }));

    const status = await screen.findByRole('status');
    expect(status).toHaveTextContent(/if that address has an account/i);
    // The provider's own rejection text must never reach the page.
    expect(status.textContent).not.toMatch(/user not found/i);
  });

  it('never reveals that an address is unregistered', async () => {
    resetPasswordForEmail.mockRejectedValue(new Error('boom'));
    renderAt('/auth/forgot-password', <ForgotPasswordPage />);
    await userEvent.type(screen.getByLabelText(/email address/i), 'nobody@nowhere.test');
    await userEvent.click(screen.getByRole('button', { name: /send reset link/i }));

    const status = await screen.findByRole('status');
    expect(status).toHaveTextContent(/if that address has an account/i);
    expect(status.textContent).not.toMatch(/boom|no such user|not found/i);
  });
});

describe('ResetPasswordPage — link validation', () => {
  it('shows the invalid state when no link is present', async () => {
    renderAt('/auth/reset-password', <ResetPasswordPage />);
    expect(
      await screen.findByRole('heading', { name: /link not valid/i }),
    ).toBeInTheDocument();
    expect(exchangeCodeForSession).not.toHaveBeenCalled();
  });

  it('exchanges a PKCE code and shows the form', async () => {
    renderAt('/auth/reset-password?code=otp-1', <ResetPasswordPage />);
    expect(
      await screen.findByLabelText(/^new password$/i),
    ).toBeInTheDocument();
    expect(exchangeCodeForSession).toHaveBeenCalledWith('otp-1');
  });

  it('establishes an implicit session from the fragment', async () => {
    renderAt(
      '/auth/reset-password#access_token=at-1&refresh_token=rt-1&type=recovery',
      <ResetPasswordPage />,
    );
    expect(await screen.findByLabelText(/^new password$/i)).toBeInTheDocument();
    expect(setSession).toHaveBeenCalledWith({
      access_token: 'at-1',
      refresh_token: 'rt-1',
    });
  });

  it('scrubs the code from the URL before any network call', async () => {
    renderAt('/auth/reset-password?code=otp-secret', <ResetPasswordPage />);
    await screen.findByLabelText(/^new password$/i);
    expect(window.location.search).toBe('');
    expect(window.location.hash).toBe('');
  });

  it('shows the expired state when the OTP has expired', async () => {
    exchangeCodeForSession.mockResolvedValue({
      data: {},
      error: { code: 'otp_expired', message: 'expired' },
    });
    renderAt('/auth/reset-password?code=otp-1', <ResetPasswordPage />);
    expect(
      await screen.findByRole('heading', { name: /link expired/i }),
    ).toBeInTheDocument();
  });

  it('shows the invalid state when the exchange is rejected', async () => {
    exchangeCodeForSession.mockResolvedValue({
      data: {},
      error: { code: 'invalid_grant', message: 'bad code' },
    });
    renderAt('/auth/reset-password?code=otp-1', <ResetPasswordPage />);
    expect(
      await screen.findByRole('heading', { name: /link not valid/i }),
    ).toBeInTheDocument();
  });
});

describe('ResetPasswordPage — password update', () => {
  const STRONG = 'correct horse battery staple';

  it('updates the password, signs out, and shows success', async () => {
    renderAt('/auth/reset-password?code=otp-1', <ResetPasswordPage />);
    await screen.findByLabelText(/^new password$/i);

    await userEvent.type(screen.getByLabelText(/^new password$/i), STRONG);
    await userEvent.type(screen.getByLabelText(/confirm new password/i), STRONG);
    await userEvent.click(screen.getByRole('button', { name: /update password/i }));

    expect(
      await screen.findByRole('heading', { name: /password updated/i }),
    ).toBeInTheDocument();
    expect(updateUser).toHaveBeenCalledWith({ password: STRONG });
    expect(signOut).toHaveBeenCalledTimes(1);
  });

  it('rejects a mismatched confirmation without calling the API', async () => {
    renderAt('/auth/reset-password?code=otp-1', <ResetPasswordPage />);
    await screen.findByLabelText(/^new password$/i);

    await userEvent.type(screen.getByLabelText(/^new password$/i), STRONG);
    await userEvent.type(screen.getByLabelText(/confirm new password/i), 'different');
    await userEvent.click(screen.getByRole('button', { name: /update password/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/do not match/i);
    expect(updateUser).not.toHaveBeenCalled();
  });

  it('rejects a too-short password without calling the API', async () => {
    renderAt('/auth/reset-password?code=otp-1', <ResetPasswordPage />);
    await screen.findByLabelText(/^new password$/i);

    await userEvent.type(screen.getByLabelText(/^new password$/i), 'short');
    await userEvent.type(screen.getByLabelText(/confirm new password/i), 'short');
    await userEvent.click(screen.getByRole('button', { name: /update password/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/at least/i);
    expect(updateUser).not.toHaveBeenCalled();
  });

  it('surfaces a weak-password rejection from the server', async () => {
    updateUser.mockResolvedValue({
      data: {},
      error: { code: 'weak_password', message: 'leaked in a breach' },
    });
    renderAt('/auth/reset-password?code=otp-1', <ResetPasswordPage />);
    await screen.findByLabelText(/^new password$/i);

    await userEvent.type(screen.getByLabelText(/^new password$/i), STRONG);
    await userEvent.type(screen.getByLabelText(/confirm new password/i), STRONG);
    await userEvent.click(screen.getByRole('button', { name: /update password/i }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/too weak/i);
    expect(alert.textContent).not.toContain('leaked in a breach');
    expect(signOut).not.toHaveBeenCalled();
  });
});