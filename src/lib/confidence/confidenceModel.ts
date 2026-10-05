import { ConfidenceBreakdown, ConfidenceLevel, EntityClassification, MatchStatus } from '../../types';

export function computeConfidenceDimensions(params: {
  rawText: string;
  classification: EntityClassification;
  matchStatus: MatchStatus;
  hasAdditiveIdentifier: boolean;
  hasTypo: boolean;
  isMixture: boolean;
  chemicalEntityId: string | null;
  overallOcrConfidence?: string;
}): {
  confidence: ConfidenceLevel;
  confidenceScore: number;
  breakdown: ConfidenceBreakdown;
} {
  const {
    rawText,
    classification,
    matchStatus,
    hasAdditiveIdentifier,
    hasTypo,
    chemicalEntityId,
    overallOcrConfidence = 'High',
  } = params;

  // 1. OCR Confidence
  const ocrConf = hasTypo ? 'Uncertain (Typo Detected)' : overallOcrConfidence;

  // 2. Parsing Confidence: High if syntax parsed cleanly
  const parsingConf = rawText.includes('(') && !rawText.includes(')') ? 'Medium (Unmatched Paren)' : 'High';

  // 3. Normalization Confidence: High if clean tokens, Medium if syntax stripped
  const normConf = hasTypo ? 'Medium' : 'High';

  // 4. Entity Match Confidence
  let entityMatchConf: string;
  let overallLevel: ConfidenceLevel = 'High';
  let score = 95;

  if (hasAdditiveIdentifier) {
    entityMatchConf = 'High (Statutory Additive Code Verified)';
    score = 98;
    overallLevel = 'High';
  } else if (classification === 'DEFINED_SINGLE_MOLECULE' || classification === 'KNOWN_INORGANIC_ENTITY') {
    entityMatchConf = 'High (Registry Match)';
    score = 99;
    overallLevel = 'High';
  } else if (classification === 'KNOWN_COMPLEX_MIXTURE' || classification === 'KNOWN_FORMULATION_COMPONENT') {
    entityMatchConf = 'High (Known Botanical / Food Matrix)';
    score = 94;
    overallLevel = 'High';
  } else if (classification === 'OCR_UNCERTAIN') {
    entityMatchConf = 'Uncertain (Pending Human Correction)';
    score = 65;
    overallLevel = 'Medium';
  } else if (classification === 'AMBIGUOUS') {
    entityMatchConf = 'Unresolved (Umbrella Descriptor)';
    score = 40;
    overallLevel = 'Unresolved';
  } else {
    entityMatchConf = 'Unknown (No Registry Record)';
    score = 30;
    overallLevel = 'Unresolved';
  }

  // 5. Chemistry Confidence
  let chemConf: string;
  if (chemicalEntityId && (classification === 'DEFINED_SINGLE_MOLECULE' || classification === 'KNOWN_INORGANIC_ENTITY')) {
    chemConf = 'Verified (Stoichiometric Constants Available)';
  } else if (classification === 'KNOWN_COMPLEX_MIXTURE' || classification === 'KNOWN_FORMULATION_COMPONENT') {
    chemConf = 'Matrix Characterized (No Single Discrete Molecule)';
  } else {
    chemConf = 'Not Applicable / Unresolved';
  }

  return {
    confidence: overallLevel,
    confidenceScore: score,
    breakdown: {
      ocrConfidence: ocrConf,
      parsingConfidence: parsingConf,
      normalizationConfidence: normConf,
      entityMatchConfidence: entityMatchConf,
      chemistryConfidence: chemConf,
    },
  };
}
