import { createClient, type SupabaseClient } from '@supabase/supabase-js';

import { readPublicConfig } from './config';

/**
 * Single Supabase client for the app.
 *
 * `detectSessionInUrl: false` is deliberate: this app parses and scrubs the
 * recovery URL itself (see lib/recovery.ts) instead of letting the client read
 * it implicitly. That makes token handling deterministic and keeps the
 * recovery code from being browser-dependent.
 */
let client: SupabaseClient | null = null;

export function getSupabase(): SupabaseClient {
  if (client) return client;
  const config = readPublicConfig(
    import.meta.env as unknown as Record<string, string | undefined>,
  );
  client = createClient(config.supabaseUrl, config.supabaseAnonKey, {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: false,
    },
  });
  return client;
}

/** Test seam: drop the memoised client. */
export function resetSupabaseForTests(): void {
  client = null;
}