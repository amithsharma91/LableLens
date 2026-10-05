import { IngredientObservation, MatchStatus, ConfidenceLevel, OcrResponse, OcrIngredientCandidate } from '../types';
import { DEMO_CHEMICAL_ENTITIES } from '../data/chemicalEntities';

export interface ExtractedToken {
  id: string;
  originalText: string;
  editedText: string;
  position: number;
  hasTypoWarning?: boolean;
  suggestedCorrection?: string;
  matchedEntityId: string | null;
  matchStatus: MatchStatus;
  confidence: ConfidenceLevel;
}

// Map of canonical references for normalization after user review
const NORMALIZATION_LOOKUP: Record<string, {
  canonicalName: string;
  entityId: string | null;
  defaultRole: string;
  isLikelyTypo?: boolean;
  correction?: string;
  defaultEvidence: string[];
}> = {
  // Exact matches
  'sugar': { canonicalName: 'Sugar (Sucrose)', entityId: 'entity_sucrose', defaultRole: 'Bulking Sweetener', defaultEvidence: ['ev_efsa_sucrose'] },
  'cane sugar': { canonicalName: 'Sugar (Sucrose)', entityId: 'entity_sucrose', defaultRole: 'Bulking Sweetener', defaultEvidence: ['ev_efsa_sucrose'] },
  'sucrose': { canonicalName: 'Sucrose', entityId: 'entity_sucrose', defaultRole: 'Sweetener & Bulking Agent', defaultEvidence: ['ev_efsa_sucrose'] },
  
  'cocoa powder': { canonicalName: 'Cocoa powder', entityId: 'entity_cocoa_powder', defaultRole: 'Flavoring & Food Base', defaultEvidence: ['ev_fao_cocoa'] },
  'cocoa': { canonicalName: 'Cocoa powder', entityId: 'entity_cocoa_powder', defaultRole: 'Flavoring & Food Base', defaultEvidence: ['ev_fao_cocoa'] },
  
  'whey powder': { canonicalName: 'Whey powder', entityId: 'entity_whey_powder', defaultRole: 'Bulking & Dairy Solids', defaultEvidence: ['ev_fao_cocoa'] },
  
  // OCR TYPO SCENARIO (Never auto-corrected; flagged as warning for human review)
  'emulsifer': {
    canonicalName: 'Emulsifier (Lecithin)',
    entityId: 'entity_lecithin',
    defaultRole: 'Interfacial Emulsifier',
    isLikelyTypo: true,
    correction: 'Emulsifier',
    defaultEvidence: ['ev_fda_lecithin']
  },
  'emulsifier': { canonicalName: 'Emulsifier (Lecithin)', entityId: 'entity_lecithin', defaultRole: 'Interfacial Emulsifier', defaultEvidence: ['ev_fda_lecithin'] },
  'lecithin': { canonicalName: 'Lecithin', entityId: 'entity_lecithin', defaultRole: 'Interfacial Surfactant', defaultEvidence: ['ev_fda_lecithin'] },
  'soy lecithin': { canonicalName: 'Soy Lecithin', entityId: 'entity_lecithin', defaultRole: 'Interfacial Surfactant', defaultEvidence: ['ev_fda_lecithin'] },
  'sunflower lecithin': { canonicalName: 'Sunflower Lecithin', entityId: 'entity_lecithin', defaultRole: 'Interfacial Surfactant', defaultEvidence: ['ev_fda_lecithin'] },
  
  'salt': { canonicalName: 'Salt (Sodium Chloride)', entityId: 'entity_sodium_chloride', defaultRole: 'Flavor Modulator & Osmotic Agent', defaultEvidence: ['ev_codex_salt'] },
  'sea salt': { canonicalName: 'Sodium Chloride (Marine origin)', entityId: 'entity_sodium_chloride', defaultRole: 'Flavor Modulator', defaultEvidence: ['ev_codex_salt'] },
  'sodium chloride': { canonicalName: 'Sodium Chloride', entityId: 'entity_sodium_chloride', defaultRole: 'Osmotic & Flavor Agent', defaultEvidence: ['ev_codex_salt'] },

  // DELIBERATE UNRESOLVED DEMO SCENARIO:
  'natural flavouring': {
    canonicalName: 'Natural flavouring',
    entityId: null, // Deliberately null!
    defaultRole: 'Aroma & Sensory Modifier',
    defaultEvidence: ['ev_efsa_flavouring_uncertainty']
  },
  'natural flavoring': {
    canonicalName: 'Natural flavouring',
    entityId: null,
    defaultRole: 'Aroma & Sensory Modifier',
    defaultEvidence: ['ev_efsa_flavouring_uncertainty']
  },
  'flavouring': { canonicalName: 'Flavouring', entityId: null, defaultRole: 'Sensory Modifier', defaultEvidence: ['ev_efsa_flavouring_uncertainty'] },

  // Other demo ingredients
  'water': { canonicalName: 'Aqua (Water)', entityId: null, defaultRole: 'Aqueous Solvent Base', defaultEvidence: [] },
  'aqua': { canonicalName: 'Aqua (Water)', entityId: null, defaultRole: 'Aqueous Solvent Base', defaultEvidence: [] },
  'oat base': { canonicalName: 'Oat Base / Extract', entityId: 'entity_oat_base', defaultRole: 'Liquid Base & Carbohydrate Source', defaultEvidence: ['ev_efsa_flavouring_uncertainty'] },
  'oats': { canonicalName: 'Oat Base / Extract', entityId: 'entity_oat_base', defaultRole: 'Cereal Grain Base', defaultEvidence: ['ev_efsa_flavouring_uncertainty'] },
  'glycerin': { canonicalName: 'Glycerol', entityId: 'entity_glycerol', defaultRole: 'Humectant', defaultEvidence: ['ev_cir_glycerin'] },
  'glycerol': { canonicalName: 'Glycerol', entityId: 'entity_glycerol', defaultRole: 'Humectant', defaultEvidence: ['ev_cir_glycerin'] },
  'citric acid': { canonicalName: 'Citric Acid', entityId: 'entity_citric_acid', defaultRole: 'Acidulant & pH Buffer', defaultEvidence: ['ev_efsa_citric_acid'] },
  'zinc oxide': { canonicalName: 'Zinc Oxide', entityId: 'entity_zinc_oxide', defaultRole: 'Physical UV Filter', defaultEvidence: ['ev_fda_zinc_oxide'] },
  'caffeine': { canonicalName: 'Caffeine', entityId: 'entity_caffeine', defaultRole: 'Central Nervous System Stimulant', defaultEvidence: ['ev_pubchem_caffeine'] },
  'dipotassium phosphate': { canonicalName: 'Dipotassium Phosphate', entityId: 'entity_dipotassium_phosphate', defaultRole: 'Acidity Regulator & Buffer', defaultEvidence: ['ev_efsa_citric_acid'] },
  'xanthan gum': { canonicalName: 'Xanthan Gum', entityId: 'entity_xanthan_gum', defaultRole: 'Rheology Modifier', defaultEvidence: ['ev_cir_glycerin'] },
  'coco-glucoside': { canonicalName: 'Coco-Glucoside', entityId: 'entity_coco_glucoside', defaultRole: 'Mild Surfactant', defaultEvidence: ['ev_cir_glycerin'] },
};

/**
 * Sends image data to server-side Gemini Vision OCR endpoint.
 */
export async function performServerSideOcr(imageBase64: string, mimeType: string = 'image/jpeg'): Promise<OcrResponse> {
  const response = await fetch('/api/ocr', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      image: imageBase64,
      mimeType,
    }),
  });

  const data = await response.json();

  if (!response.ok) {
    const errorMsg = data?.error || 'OCR request failed.';
    const error = new Error(errorMsg) as any;
    error.code = data?.code || 'OCR_ERROR';
    error.status = response.status;
    throw error;
  }

  return data as OcrResponse;
}

/**
 * Transforms raw structured OCR candidates into ExtractedToken objects for the Review Screen.
 * Strictly preserves the verbatim raw text as `editedText` initially; never silently auto-fixes spelling!
 */
export function buildTokensFromOcrCandidates(
  candidates: OcrIngredientCandidate[],
  warnings: string[] = []
): ExtractedToken[] {
  return candidates.map((candidate, index) => {
    const raw = candidate.raw_text.trim();
    const cleanLower = raw.toLowerCase().replace(/[()0-9%]/g, '').trim();
    const lookup = NORMALIZATION_LOOKUP[cleanLower];

    // Check for typo warnings without auto-correcting
    const isTypo = lookup?.isLikelyTypo || cleanLower === 'emulsifer' ||
      warnings.some(w => w.toLowerCase().includes(cleanLower));
    const suggestion = lookup?.correction || (cleanLower === 'emulsifer' ? 'Emulsifier' : undefined);

    let matchStatus: MatchStatus = 'Unknown';
    let confidence: ConfidenceLevel = 'Unresolved';

    if (lookup) {
      if (lookup.entityId) {
        matchStatus = isTypo ? 'Partially matched' : 'Matched';
        confidence = isTypo ? 'Medium' : 'High';
      } else {
        matchStatus = 'Unknown';
        confidence = 'Unresolved';
      }
    } else {
      const matchedEnt = Object.values(DEMO_CHEMICAL_ENTITIES).find(e =>
        e.preferredName.toLowerCase() === cleanLower ||
        e.aliases.some(a => a.toLowerCase() === cleanLower)
      );
      if (matchedEnt) {
        matchStatus = 'Matched';
        confidence = 'High';
      }
    }

    return {
      id: `tok_${index}_${Date.now()}`,
      originalText: raw,
      editedText: raw, // Verbatim! Must NOT auto-replace
      position: candidate.position || index + 1,
      hasTypoWarning: isTypo,
      suggestedCorrection: suggestion,
      matchedEntityId: lookup?.entityId || null,
      matchStatus,
      confidence,
    };
  });
}

/**
 * Manual text fallback: splits raw text lines/commas into tokens.
 */
export function parseRawLabelText(rawText: string): ExtractedToken[] {
  const cleanTokens = rawText
    .split(/[,;\n]+/)
    .map(t => t.trim())
    .filter(t => t.length > 0);

  const candidates: OcrIngredientCandidate[] = cleanTokens.map((t, i) => ({
    raw_text: t,
    position: i + 1,
  }));

  return buildTokensFromOcrCandidates(candidates);
}

/**
 * Converts validated/edited tokens into verified IngredientObservation objects for chemical analysis.
 */
export function buildObservationsFromTokens(tokens: ExtractedToken[]): IngredientObservation[] {
  return tokens.map((t, idx) => {
    const textToMatch = t.editedText.trim();
    const lower = textToMatch.toLowerCase().replace(/[()0-9%]/g, '').trim();
    const lookup = NORMALIZATION_LOOKUP[lower];

    const wasTypoCorrected = t.originalText !== t.editedText;

    let entityId = lookup?.entityId || null;
    let matchStatus: MatchStatus = lookup?.entityId ? 'Matched' : 'Unknown';
    let confidence: ConfidenceLevel = lookup?.entityId ? 'High' : 'Unresolved';
    let score = lookup?.entityId ? 96 : 35;
    let role = lookup?.defaultRole || 'Formulation Component';
    let evidenceIds = lookup?.defaultEvidence || [];

    if (!lookup) {
      const foundEntity = Object.values(DEMO_CHEMICAL_ENTITIES).find(e =>
        e.preferredName.toLowerCase() === lower ||
        e.aliases.some(a => a.toLowerCase() === lower)
      );
      if (foundEntity) {
        entityId = foundEntity.id;
        matchStatus = 'Matched';
        confidence = 'High';
        score = 95;
        role = foundEntity.chemicalClass;
      }
    }

    // Deliberate unresolved case: "Natural flavouring"
    if (lower.includes('natural flavour') || lower.includes('natural flavor')) {
      entityId = null;
      matchStatus = 'Unknown';
      confidence = 'Unresolved';
      score = 30;
      role = 'Aroma & Sensory Modifier';
      evidenceIds = ['ev_efsa_flavouring_uncertainty'];
    }

    let whyData = undefined;
    if (entityId) {
      const entity = DEMO_CHEMICAL_ENTITIES[entityId];
      whyData = {
        whatIsIt: `${entity.preferredName} (${entity.chemicalClass}).`,
        whyUsed: `Functions as ${role.toLowerCase()} in this product matrix.`,
        relevantChemistry: entity.descriptors.join('. ') + '.',
        evidenceSupport: `Documented in authoritative literature (${evidenceIds.join(', ')}).`,
        uncertainties: entity.limitations || 'Exact industrial grade and concentration remain proprietary to manufacturer.'
      };
    } else if (matchStatus === 'Unknown') {
      whyData = {
        whatIsIt: 'Unresolved or composite formulation component.',
        whyUsed: 'Provides sensory or auxiliary stabilizing properties.',
        relevantChemistry: 'Not resolvable to an empirical single molecular representation from label text alone.',
        evidenceSupport: 'EFSA guidance acknowledges multi-constituent mixtures cannot be isolated without mass spectrometry analysis.',
        uncertainties: 'Not confidently resolved to a single chemical entity. Do not invent a molecular structure for it.'
      };
    }

    return {
      id: `obs_${idx}_${Date.now()}`,
      rawText: t.originalText,
      normalizedText: lookup?.canonicalName || textToMatch,
      matchStatus,
      chemicalEntityId: entityId,
      role,
      confidence,
      confidenceScore: score,
      evidenceIds,
      whyIsThisHere: whyData,
      isCustomEdited: wasTypoCorrected,
    };
  });
}
