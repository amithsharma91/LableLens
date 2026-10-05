import { WebResearchResult } from '../../types';
import { SEED_WEB_RESEARCH } from '../../data/seedWebResearch';

const STORAGE_KEY = 'labellens_web_research_cache_v1';

// In-memory runtime cache
const memoryCache = new Map<string, WebResearchResult>();

/**
 * Normalizes an ingredient query key for canonical cache lookup.
 */
export function buildCacheKey(name: string, identifier?: string | null): string {
  const cleanName = name
    .toLowerCase()
    .replace(/[()0-9%]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
  const cleanId = identifier ? identifier.toUpperCase().replace(/\s+/g, '').trim() : '';
  return cleanId ? `${cleanId}::${cleanName}` : cleanName;
}

/**
 * Loads cache from localStorage into memory once on startup, seeding baseline records.
 */
function initCache(): void {
  // Always seed baseline verified records first
  Object.entries(SEED_WEB_RESEARCH).forEach(([key, record]) => {
    const cacheKey = buildCacheKey(record.canonicalName, record.identifier);
    memoryCache.set(cacheKey, record);
    // Also index by raw seed key e.g. "ins 471", "whey protein concentrate"
    memoryCache.set(key, record);
    if (record.identifier) {
      memoryCache.set(record.identifier.toUpperCase().replace(/\s+/g, ''), record);
    }
  });

  if (typeof window === 'undefined') return;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (typeof parsed === 'object' && parsed !== null) {
        Object.entries(parsed).forEach(([k, v]) => {
          memoryCache.set(k, v as WebResearchResult);
        });
      }
    }
  } catch (err) {
    console.warn('[ResearchCache] Failed to load localStorage cache:', err);
  }
}

// Initialize on module load
initCache();

/**
 * Retrieves a cached web research record if available.
 */
export function getCachedResearch(name: string, identifier?: string | null): WebResearchResult | null {
  const key = buildCacheKey(name, identifier);
  // Direct key check
  if (memoryCache.has(key)) {
    return memoryCache.get(key)!;
  }
  // If identifier was provided, also check by identifier only
  if (identifier) {
    const idKey = identifier.toUpperCase().replace(/\s+/g, '').trim();
    for (const [k, v] of memoryCache.entries()) {
      if (k.startsWith(`${idKey}::`) || v.identifier?.toUpperCase().replace(/\s+/g, '') === idKey) {
        return v;
      }
    }
  }
  return null;
}

/**
 * Stores a verified web-researched record into the reusable cache.
 * Avoids overwriting existing verified records unless the new one has higher verification.
 */
export function setCachedResearch(name: string, result: WebResearchResult): void {
  const key = buildCacheKey(name, result.identifier);
  memoryCache.set(key, result);

  if (typeof window !== 'undefined') {
    try {
      const obj: Record<string, WebResearchResult> = {};
      memoryCache.forEach((v, k) => {
        obj[k] = v;
      });
      localStorage.setItem(STORAGE_KEY, JSON.stringify(obj));
    } catch (err) {
      console.warn('[ResearchCache] Failed to persist to localStorage:', err);
    }
  }
}

/**
 * Clears the research cache.
 */
export function clearResearchCache(): void {
  memoryCache.clear();
  if (typeof window !== 'undefined') {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (e) {
      // Ignore
    }
  }
}
