/** Types for the build-time bundle secret guard (plain Node ESM module). */

/**
 * Classify one JWT-shaped substring.
 * Returns `null` when acceptable, otherwise a description of why it is refused.
 */
export declare function classifyJwt(token: string): string | null;

/** Return a list of finding descriptions for one file's text. */
export declare function scanText(contents: string): string[];
