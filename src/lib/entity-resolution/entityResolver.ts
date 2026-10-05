import { EntityClassification, MatchStatus, VerificationStatus, WebResearchResult } from '../../types';
import { DEMO_CHEMICAL_ENTITIES } from '../../data/chemicalEntities';
import { getCachedResearch } from '../cache/researchCache';

export interface EntityResolutionResult {
  classification: EntityClassification;
  matchStatus: MatchStatus;
  chemicalEntityId: string | null;
  canonicalName: string;
  role: string;
  evidenceIds: string[];
  isAdditiveCodeMatched: boolean;
  verificationStatus: VerificationStatus;
  isLocalCatalogMatch: boolean;
  needsWebResearch: boolean;
  webResearch?: WebResearchResult | null;
}

// Map of Curated Local Additive codes
const LOCAL_ADDITIVE_REGISTRY: Record<string, {
  entityId: string;
  canonicalName: string;
  role: string;
  evidenceIds: string[];
}> = {
  'INS 322': {
    entityId: 'entity_lecithin',
    canonicalName: 'Lecithin (INS 322)',
    role: 'Interfacial Emulsifier',
    evidenceIds: ['ev_fda_lecithin'],
  },
  'INS322': {
    entityId: 'entity_lecithin',
    canonicalName: 'Lecithin (INS 322)',
    role: 'Interfacial Emulsifier',
    evidenceIds: ['ev_fda_lecithin'],
  },
  'E 322': {
    entityId: 'entity_lecithin',
    canonicalName: 'Lecithin (E 322)',
    role: 'Interfacial Emulsifier',
    evidenceIds: ['ev_fda_lecithin'],
  },
  'E 330': {
    entityId: 'entity_citric_acid',
    canonicalName: 'Citric Acid (E 330)',
    role: 'Acidulant & pH Buffer',
    evidenceIds: ['ev_efsa_citric_acid'],
  },
  'E 340': {
    entityId: 'entity_dipotassium_phosphate',
    canonicalName: 'Dipotassium Phosphate (E 340)',
    role: 'Acidity Regulator',
    evidenceIds: ['ev_efsa_citric_acid'],
  },
  'E 415': {
    entityId: 'entity_xanthan_gum',
    canonicalName: 'Xanthan Gum (E 415)',
    role: 'Rheology Modifier',
    evidenceIds: ['ev_cir_glycerin'],
  },
};

/**
 * Resolves an ingredient's clean key and additive code against the chemical/evidence registry.
 * Priority: Local verified catalog -> Web research cache -> Trigger Web Research Required.
 */
export function resolveEntity(
  cleanKey: string,
  identifier: string | null,
  displayName: string,
  hasChildren: boolean = false
): EntityResolutionResult {
  // 1. Primary Signal: Additive Identifier in Local Registry (e.g. INS 322, E 330)
  if (identifier) {
    const normalizedId = identifier.toUpperCase().replace(/\s+/g, ' ').trim();
    const codeMatch = LOCAL_ADDITIVE_REGISTRY[normalizedId] ||
      LOCAL_ADDITIVE_REGISTRY[normalizedId.replace(/\s+/g, '')];

    if (codeMatch) {
      return {
        classification: 'KNOWN_COMPLEX_MIXTURE',
        matchStatus: 'Matched',
        chemicalEntityId: codeMatch.entityId,
        canonicalName: codeMatch.canonicalName,
        role: codeMatch.role,
        evidenceIds: codeMatch.evidenceIds,
        isAdditiveCodeMatched: true,
        verificationStatus: 'LOCAL_VERIFIED',
        isLocalCatalogMatch: true,
        needsWebResearch: false,
      };
    }
  }

  // 2. Multi-ingredient parent formulations (e.g. Peanut Butter, Dark Chocolate)
  if (hasChildren) {
    if (cleanKey.includes('peanut butter')) {
      return {
        classification: 'KNOWN_FORMULATION_COMPONENT',
        matchStatus: 'Matched',
        chemicalEntityId: null,
        canonicalName: displayName,
        role: 'Primary Nut Paste Food Base',
        evidenceIds: [],
        isAdditiveCodeMatched: false,
        verificationStatus: 'LOCAL_VERIFIED',
        isLocalCatalogMatch: true,
        needsWebResearch: false,
      };
    }
    if (cleanKey.includes('chocolate')) {
      return {
        classification: 'KNOWN_FORMULATION_COMPONENT',
        matchStatus: 'Matched',
        chemicalEntityId: null,
        canonicalName: displayName,
        role: 'Confectionery Lipid-Suspension Base',
        evidenceIds: ['ev_fao_cocoa'],
        isAdditiveCodeMatched: false,
        verificationStatus: 'LOCAL_VERIFIED',
        isLocalCatalogMatch: true,
        needsWebResearch: false,
      };
    }
    return {
      classification: 'KNOWN_FORMULATION_COMPONENT',
      matchStatus: 'Matched',
      chemicalEntityId: null,
      canonicalName: displayName,
      role: 'Composite Formulation Component',
      evidenceIds: [],
      isAdditiveCodeMatched: false,
      verificationStatus: 'LOCAL_VERIFIED',
      isLocalCatalogMatch: true,
      needsWebResearch: false,
    };
  }

  // 3. Known single molecules in Local Catalog
  if (cleanKey === 'sugar' || cleanKey === 'cane sugar' || cleanKey === 'sucrose') {
    return {
      classification: 'DEFINED_SINGLE_MOLECULE',
      matchStatus: 'Matched',
      chemicalEntityId: 'entity_sucrose',
      canonicalName: 'Sugar (Sucrose)',
      role: 'Bulking Sweetener',
      evidenceIds: ['ev_efsa_sucrose'],
      isAdditiveCodeMatched: false,
      verificationStatus: 'LOCAL_VERIFIED',
      isLocalCatalogMatch: true,
      needsWebResearch: false,
    };
  }
  if (cleanKey === 'citric acid') {
    return {
      classification: 'DEFINED_SINGLE_MOLECULE',
      matchStatus: 'Matched',
      chemicalEntityId: 'entity_citric_acid',
      canonicalName: 'Citric Acid',
      role: 'Acidulant & pH Buffer',
      evidenceIds: ['ev_efsa_citric_acid'],
      isAdditiveCodeMatched: false,
      verificationStatus: 'LOCAL_VERIFIED',
      isLocalCatalogMatch: true,
      needsWebResearch: false,
    };
  }
  if (cleanKey === 'caffeine') {
    return {
      classification: 'DEFINED_SINGLE_MOLECULE',
      matchStatus: 'Matched',
      chemicalEntityId: 'entity_caffeine',
      canonicalName: 'Caffeine',
      role: 'Central Nervous System Stimulant',
      evidenceIds: ['ev_pubchem_caffeine'],
      isAdditiveCodeMatched: false,
      verificationStatus: 'LOCAL_VERIFIED',
      isLocalCatalogMatch: true,
      needsWebResearch: false,
    };
  }
  if (cleanKey === 'glycerin' || cleanKey === 'glycerol') {
    return {
      classification: 'DEFINED_SINGLE_MOLECULE',
      matchStatus: 'Matched',
      chemicalEntityId: 'entity_glycerol',
      canonicalName: 'Glycerol',
      role: 'Humectant & Dermal Conditioning Agent',
      evidenceIds: ['ev_cir_glycerin'],
      isAdditiveCodeMatched: false,
      verificationStatus: 'LOCAL_VERIFIED',
      isLocalCatalogMatch: true,
      needsWebResearch: false,
    };
  }

  // 4. Known inorganic entities in Local Catalog
  if (cleanKey === 'salt' || cleanKey === 'sea salt' || cleanKey === 'sodium chloride') {
    return {
      classification: 'KNOWN_INORGANIC_ENTITY',
      matchStatus: 'Matched',
      chemicalEntityId: 'entity_sodium_chloride',
      canonicalName: 'Salt (Sodium Chloride)',
      role: 'Flavor Modulator & Osmotic Agent',
      evidenceIds: ['ev_codex_salt'],
      isAdditiveCodeMatched: false,
      verificationStatus: 'LOCAL_VERIFIED',
      isLocalCatalogMatch: true,
      needsWebResearch: false,
    };
  }
  if (cleanKey.includes('zinc oxide')) {
    return {
      classification: 'KNOWN_INORGANIC_ENTITY',
      matchStatus: 'Matched',
      chemicalEntityId: 'entity_zinc_oxide',
      canonicalName: 'Zinc Oxide',
      role: 'Physical UV Filter',
      evidenceIds: ['ev_fda_zinc_oxide'],
      isAdditiveCodeMatched: false,
      verificationStatus: 'LOCAL_VERIFIED',
      isLocalCatalogMatch: true,
      needsWebResearch: false,
    };
  }
  if (cleanKey.includes('dipotassium phosphate')) {
    return {
      classification: 'KNOWN_INORGANIC_ENTITY',
      matchStatus: 'Matched',
      chemicalEntityId: 'entity_dipotassium_phosphate',
      canonicalName: 'Dipotassium Phosphate',
      role: 'Acidity Regulator & Buffer',
      evidenceIds: ['ev_efsa_citric_acid'],
      isAdditiveCodeMatched: false,
      verificationStatus: 'LOCAL_VERIFIED',
      isLocalCatalogMatch: true,
      needsWebResearch: false,
    };
  }

  // 5. Known complex biological materials & extracts in Local Catalog
  if (cleanKey === 'peanut' || cleanKey === 'peanuts' || cleanKey.includes('roasted peanut')) {
    return {
      classification: 'KNOWN_COMPLEX_MIXTURE',
      matchStatus: 'Matched',
      chemicalEntityId: 'entity_peanut',
      canonicalName: 'Peanut (Arachis hypogaea)',
      role: 'Lipid & Protein Food Base',
      evidenceIds: [],
      isAdditiveCodeMatched: false,
      verificationStatus: 'LOCAL_VERIFIED',
      isLocalCatalogMatch: true,
      needsWebResearch: false,
    };
  }
  if (cleanKey === 'cocoa butter' || cleanKey.includes('cacao butter')) {
    return {
      classification: 'KNOWN_COMPLEX_MIXTURE',
      matchStatus: 'Matched',
      chemicalEntityId: 'entity_cocoa_butter',
      canonicalName: 'Cocoa Butter',
      role: 'Confectionery Continuous Lipid Phase',
      evidenceIds: ['ev_fao_cocoa'],
      isAdditiveCodeMatched: false,
      verificationStatus: 'LOCAL_VERIFIED',
      isLocalCatalogMatch: true,
      needsWebResearch: false,
    };
  }
  if (cleanKey === 'cocoa powder' || cleanKey === 'cocoa' || cleanKey.includes('cocoa solids')) {
    return {
      classification: 'KNOWN_COMPLEX_MIXTURE',
      matchStatus: 'Matched',
      chemicalEntityId: 'entity_cocoa_powder',
      canonicalName: 'Cocoa Powder',
      role: 'Chocolate Flavoring & Non-Fat Solids',
      evidenceIds: ['ev_fao_cocoa'],
      isAdditiveCodeMatched: false,
      verificationStatus: 'LOCAL_VERIFIED',
      isLocalCatalogMatch: true,
      needsWebResearch: false,
    };
  }
  if (cleanKey === 'lecithin' || cleanKey.includes('soy lecithin') || cleanKey.includes('sunflower lecithin')) {
    return {
      classification: 'KNOWN_COMPLEX_MIXTURE',
      matchStatus: 'Matched',
      chemicalEntityId: 'entity_lecithin',
      canonicalName: 'Lecithin (Phospholipid Complex)',
      role: 'Interfacial Surfactant',
      evidenceIds: ['ev_fda_lecithin'],
      isAdditiveCodeMatched: false,
      verificationStatus: 'LOCAL_VERIFIED',
      isLocalCatalogMatch: true,
      needsWebResearch: false,
    };
  }
  if (cleanKey.includes('oat base') || cleanKey === 'oats') {
    return {
      classification: 'KNOWN_COMPLEX_MIXTURE',
      matchStatus: 'Matched',
      chemicalEntityId: 'entity_oat_base',
      canonicalName: 'Oat Base / Extract',
      role: 'Cereal Liquid Base',
      evidenceIds: ['ev_efsa_flavouring_uncertainty'],
      isAdditiveCodeMatched: false,
      verificationStatus: 'LOCAL_VERIFIED',
      isLocalCatalogMatch: true,
      needsWebResearch: false,
    };
  }

  // 6. Typo Warning (e.g. "Emulsifer")
  if (cleanKey === 'emulsifer') {
    return {
      classification: 'OCR_UNCERTAIN',
      matchStatus: 'Partially matched',
      chemicalEntityId: 'entity_lecithin',
      canonicalName: displayName,
      role: 'Interfacial Emulsifier (Pending Typo Correction)',
      evidenceIds: ['ev_fda_lecithin'],
      isAdditiveCodeMatched: false,
      verificationStatus: 'LOCAL_VERIFIED',
      isLocalCatalogMatch: true,
      needsWebResearch: false,
    };
  }

  // 7. Check Web Research Cache before declaring uncataloged (Avoid unnecessary search!)
  const cachedResearch = getCachedResearch(displayName, identifier);
  if (cachedResearch) {
    return {
      classification: cachedResearch.entityType,
      matchStatus: cachedResearch.isSufficientlyVerified ? 'Matched' : 'Unknown',
      chemicalEntityId: null,
      canonicalName: cachedResearch.canonicalName,
      role: cachedResearch.functionalRole,
      evidenceIds: [],
      isAdditiveCodeMatched: Boolean(cachedResearch.identifier),
      verificationStatus: cachedResearch.verificationStatus,
      isLocalCatalogMatch: false,
      needsWebResearch: false,
      webResearch: cachedResearch,
    };
  }

  // 8. Deliberate uncataloged / ambiguous ingredients (e.g. INS 471, Whey Protein, Jaggery, Natural Flavouring)
  // Flag as "Web Research Required"
  const isAmbiguousFlavour = cleanKey.includes('flavour') || cleanKey.includes('flavor') || cleanKey.includes('fragrance');

  return {
    classification: isAmbiguousFlavour ? 'AMBIGUOUS' : 'UNKNOWN',
    matchStatus: 'Unknown',
    chemicalEntityId: null,
    canonicalName: displayName,
    role: isAmbiguousFlavour ? 'Aroma & Sensory Modifier' : 'Formulation Component',
    evidenceIds: isAmbiguousFlavour ? ['ev_efsa_flavouring_uncertainty'] : [],
    isAdditiveCodeMatched: Boolean(identifier),
    verificationStatus: 'UNRESOLVED_UNKNOWN',
    isLocalCatalogMatch: false,
    needsWebResearch: true,
    webResearch: null,
  };
}
