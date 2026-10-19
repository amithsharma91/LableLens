#!/usr/bin/env node
/**
 * Build-time guard: refuse to ship a client bundle containing privileged
 * credentials or token material.
 *
 * WHAT IS AND IS NOT ALLOWED
 *
 *   ALLOWED  a modern publishable key  sb_publishable_...
 *   ALLOWED  a legacy JWT whose role claim is exactly the browser role
 *            (this is the legitimate Supabase anon key, and it is EXPECTED in
 *             the bundle — the browser cannot authenticate without it)
 *   REFUSED  any other JWT: a privileged one, or one whose payload cannot be
 *            decoded / carries no role claim (fail closed)
 *   REFUSED  new-style privileged keys, and privileged names in plaintext
 *
 * The JWT decision is delegated to shared/public-key-rules.js, the same
 * predicate the runtime validator uses, so the two cannot drift apart. This
 * file only adds the plain-substring rules, which belong here because this
 * script is executed by Node and is never part of the client bundle.
 *
 * It runs as part of `npm run build`, after `vite build`. On a hit it prints
 * the pattern that matched but NEVER the matched text, so running it cannot
 * leak a secret into CI logs.
 *
 * Usage: node scripts/check-bundle-secrets.mjs [distDir]
 */

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import process from 'node:process';

import { isPublishableKey, jwtRole } from '../shared/public-key-rules.js';

// Resolved lazily inside main(): when this module is imported by the test
// runner, import.meta.url is not a file: URL, so resolving it at import time
// would throw before any test ran.
function resolveDist() {
  if (process.argv[2]) return process.argv[2];
  return join(fileURLToPath(new URL('..', import.meta.url)), 'dist');
}

/** Plaintext rules. These literals live only in this Node-side script. */
const PLAINTEXT_RULES = [
  { name: 'new-style privileged key', pattern: /sb_secret_[A-Za-z0-9_-]+/ },
  { name: 'privileged role name in plaintext', pattern: /service_role/ },
  { name: 'privileged env var name', pattern: /SUPABASE_SERVICE_ROLE/ },
];

/** Three base64url segments. Matches legacy keys and every JWT. */
const JWT_PATTERN =
  /eyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}/g;

const SCAN_EXTENSIONS = ['.js', '.mjs', '.css', '.html', '.map'];

/**
 * Classify one JWT-shaped substring.
 * `null` means acceptable; otherwise a description of why it is refused.
 *
 * The description never includes any part of the token, including the decoded
 * role value: a message that echoes content derived from the credential would
 * put attacker-influenceable text into CI logs.
 */
export function classifyJwt(token) {
  if (isPublishableKey(token)) return null; // role === browser role
  const role = jwtRole(token);
  if (role === null) return 'unrecognised or malformed JWT';
  return 'JWT with a privileged or non-browser role claim';
}

/** Return a list of finding descriptions for one file's text. */
export function scanText(contents) {
  const findings = [];
  for (const { name, pattern } of PLAINTEXT_RULES) {
    if (pattern.test(contents)) findings.push(name);
  }
  for (const match of contents.matchAll(JWT_PATTERN)) {
    const problem = classifyJwt(match[0]);
    if (problem) findings.push(problem);
  }
  return findings;
}

function* walk(dir) {
  let entries;
  try {
    entries = readdirSync(dir);
  } catch {
    return;
  }
  for (const entry of entries) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      yield* walk(full);
    } else if (SCAN_EXTENSIONS.some((ext) => entry.endsWith(ext))) {
      yield full;
    }
  }
}

function main() {
  const dist = resolveDist();
  const findings = [];
  let files = 0;

  for (const file of walk(dist)) {
    files += 1;
    for (const problem of scanText(readFileSync(file, 'utf8'))) {
      findings.push({ file: relative(dist, file), problem });
    }
  }

  if (findings.length > 0) {
    console.error('\ncheck-bundle-secrets: BUILD REFUSED\n');
    for (const finding of findings) {
      console.error(`  ${finding.file}: ${finding.problem}`);
    }
    console.error(
      '\nThe client bundle may contain the publishable anon key (role: anon) ' +
        'and nothing else.\nA privileged key would bypass row-level security. ' +
        'Values are never echoed here.\n',
    );
    process.exit(1);
  }

  console.log(
    `check-bundle-secrets: OK — scanned ${files} built file(s); only ` +
      'publishable browser key material was found.',
  );
}

// Only run the CLI when executed directly. When imported (by the regression
// tests) this module must export its predicates without scanning anything or
// calling process.exit().
if (process.argv[1] && import.meta.url === `file://${process.argv[1]}`) {
  main();
}
