/**
 * Public browser configuration.
 *
 * Vite only inlines environment variables prefixed with `VITE_` into the
 * client bundle. That prefix is the entire security boundary for this file:
 * a privileged key without the prefix is never bundled, and a privileged key
 * given the prefix is rejected below.
 *
 * The "is this key publishable?" decision is NOT reimplemented here. It is
 * imported from shared/public-key-rules.js, which the build-time bundle guard
 * (scripts/check-bundle-secrets.mjs) also uses. One predicate, two call sites,
 * so the runtime check and the build check cannot disagree — a disagreement
 * would either fail a legitimate build or let a privileged key through review.
 *
 * Source in this directory must NOT contain the literal name of any privileged
 * role or key type: those literals would be bundled and would trip the guard.
 */

import { isPublishableKey } from '../../shared/public-key-rules.js';

export { isPublishableKey };

export interface PublicConfig {
  supabaseUrl: string;
  supabaseAnonKey: string;
}

export class ConfigError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ConfigError';
  }
}

const SUPABASE_URL_PATTERN = /^https:\/\/[a-z0-9-]+\.supabase\.co$/i;

/**
 * Validate the public configuration, or throw ConfigError.
 *
 * Throwing (rather than defaulting) is deliberate: a misconfigured frontend
 * must fail loudly and visibly instead of silently attempting sign-in against
 * a wrong or privileged target.
 */
export function readPublicConfig(
  env: Record<string, string | undefined>,
): PublicConfig {
  const supabaseUrl = (env.VITE_SUPABASE_URL ?? '').trim();
  const supabaseAnonKey = (env.VITE_SUPABASE_ANON_KEY ?? '').trim();

  if (!supabaseUrl) {
    throw new ConfigError(
      'VITE_SUPABASE_URL is not set. Copy .env.example to .env.local and fill it in.',
    );
  }
  if (!supabaseAnonKey) {
    throw new ConfigError(
      'VITE_SUPABASE_ANON_KEY is not set. Copy .env.example to .env.local and fill it in.',
    );
  }
  if (!SUPABASE_URL_PATTERN.test(supabaseUrl)) {
    throw new ConfigError(
      'VITE_SUPABASE_URL must be an https://<project-ref>.supabase.co origin.',
    );
  }
  if (!isPublishableKey(supabaseAnonKey)) {
    // Never echo the value.
    throw new ConfigError(
      'VITE_SUPABASE_ANON_KEY is not a publishable browser key. The browser ' +
        'may only receive the anon key; a privileged key would bypass ' +
        'row-level security. Refusing to start.',
    );
  }

  return { supabaseUrl, supabaseAnonKey };
}
