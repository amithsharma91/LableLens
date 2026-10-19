export declare const PUBLISHABLE_PREFIX: string;
export declare const BROWSER_ROLE: string;

export declare function decodeBase64Url(segment: string): string | null;
export declare function readJwtClaims(token: string): Record<string, unknown> | null;
export declare function jwtRole(token: string): string | null;
export declare function isPublishableKey(key: unknown): boolean;
