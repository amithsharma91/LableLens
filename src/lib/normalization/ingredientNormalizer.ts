/**
 * LabelLens — Ingredient Normalizer
 * Normalizes only syntactic variation without altering chemical identity.
 * Rule: Do NOT silently replace ingredient text with a chemical name during normalization.
 */

export interface NormalizedResult {
  rawText: string;
  name: string;
  normalizedName: string;
  percentage: number | null;
  identifier: string | null;
  cleanKey: string;
}

/**
 * Strips syntactic packaging punctuation, trailing brackets, and extra spaces.
 * Preserves the exact common/printed name rather than forcing a chemical alias.
 */
export function normalizeIngredientSyntax(
  name: string,
  rawText: string,
  percentage: number | null,
  identifier: string | null
): NormalizedResult {
  // Syntactic cleaning
  let cleaned = name.trim();

  // Strip trailing colons, semicolons, dashes, asterisks
  cleaned = cleaned.replace(/[:;\-*•]+$/, '').trim();

  // Strip residual surrounding parentheses if entire string is enclosed
  if (cleaned.startsWith('(') && cleaned.endsWith(')')) {
    cleaned = cleaned.slice(1, -1).trim();
  }

  // Generate lowercase search key for entity matching
  const cleanKey = cleaned
    .toLowerCase()
    .replace(/[()0-9%]/g, '')
    .replace(/\s+/g, ' ')
    .trim();

  return {
    rawText,
    name: cleaned,
    normalizedName: cleaned, // Retains human-readable printed name!
    percentage,
    identifier,
    cleanKey,
  };
}
