import { ChemicalEntity, Domain, WebResearchResult, VerificationStatus } from '../types';
import { DEMO_CHEMICAL_ENTITIES } from '../data/chemicalEntities';
import { getCachedResearch, setCachedResearch } from '../lib/cache/researchCache';

export interface ResearchOutcome {
  verificationStatus: VerificationStatus;
  localEntity: ChemicalEntity | null;
  webResearch: WebResearchResult | null;
  isFromCache: boolean;
  error?: string;
}

/**
 * Checks if an ingredient is present in the local verified LabelLens catalog.
 */
export function findLocalVerifiedEntity(cleanKey: string, identifier?: string | null): ChemicalEntity | null {
  // 1. Direct additive code lookup if present
  if (identifier) {
    const idClean = identifier.toUpperCase().replace(/\s+/g, '');
    for (const ent of Object.values(DEMO_CHEMICAL_ENTITIES)) {
      if (ent.aliases.some(a => a.toUpperCase().replace(/\s+/g, '') === idClean)) {
        return ent;
      }
      if (ent.id.toUpperCase().replace(/[^A-Z0-9]/g, '') === idClean) {
        return ent;
      }
    }
  }

  // 2. Direct name/aliases lookup
  const normKey = cleanKey.toLowerCase().trim();
  for (const ent of Object.values(DEMO_CHEMICAL_ENTITIES)) {
    if (ent.preferredName.toLowerCase() === normKey) {
      return ent;
    }
    if (ent.aliases.some(a => a.toLowerCase() === normKey)) {
      return ent;
    }
  }

  return null;
}

/**
 * Primary Entity Resolution & Web Research Fallback Pipeline:
 * STEP 1: Search local LabelLens catalog. If verified match exists -> use it; DO NOT perform unnecessary search.
 * STEP 2: Check cached web records. If present -> reuse cached verified record.
 * STEP 3: Perform Gemini Google Search Grounding research.
 * STEP 4: Validate, cache if verified, and return.
 */
export async function researchIngredientWithFallback(params: {
  ingredientName: string;
  rawText?: string;
  identifier?: string | null;
  domain?: Domain;
  category?: string;
  forceRefresh?: boolean;
}): Promise<ResearchOutcome> {
  const { ingredientName, rawText, identifier, domain = 'Food', category, forceRefresh = false } = params;

  const cleanKey = ingredientName
    .toLowerCase()
    .replace(/[()0-9%]/g, '')
    .replace(/\s+/g, ' ')
    .trim();

  // STEP 1: Search local LabelLens catalog (No unnecessary web research!)
  const localMatch = findLocalVerifiedEntity(cleanKey, identifier);
  if (localMatch && !forceRefresh) {
    return {
      verificationStatus: 'LOCAL_VERIFIED',
      localEntity: localMatch,
      webResearch: null,
      isFromCache: false,
    };
  }

  // STEP 2: Check cached web research records
  if (!forceRefresh) {
    const cached = getCachedResearch(ingredientName, identifier);
    if (cached) {
      return {
        verificationStatus: cached.verificationStatus,
        localEntity: null,
        webResearch: cached,
        isFromCache: true,
      };
    }
  }

  // STEP 3: Trigger Web Research via Gemini with Google Search Grounding
  try {
    const response = await fetch('/api/research-ingredient', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        ingredientName,
        rawText: rawText || ingredientName,
        identifier: identifier || null,
        domain,
        category,
      }),
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(errData?.error || `Research request failed with status ${response.status}`);
    }

    const result: WebResearchResult = await response.json();

    // STEP 4: Cache if verified or resolved
    if (result.isSufficientlyVerified) {
      setCachedResearch(ingredientName, result);
    }

    return {
      verificationStatus: result.verificationStatus,
      localEntity: null,
      webResearch: result,
      isFromCache: false,
    };
  } catch (error: any) {
    console.error(`[WebResearchService] Research failed for "${ingredientName}":`, error);
    return {
      verificationStatus: 'UNRESOLVED_UNKNOWN',
      localEntity: null,
      webResearch: null,
      isFromCache: false,
      error: error?.message || 'Web research service error',
    };
  }
}
