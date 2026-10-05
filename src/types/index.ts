/**
 * LabelLens — Core Data Model
 * Explicit separation between raw OCR text, structural tree parsing,
 * normalized entities, chemical facts, functional roles, and evidence.
 */

export type Domain = 'Food' | 'Beverage' | 'Cosmetics' | 'Personal Care';

export type RepresentationType =
  | 'Defined single molecule'
  | 'Inorganic mineral entity'
  | 'Complex natural mixture / extract'
  | 'Polymer / biological mixture'
  | 'Unresolved botanical / flavour';

export type MatchStatus = 'Matched' | 'Partially matched' | 'Unknown' | 'Demo data';

export type ConfidenceLevel = 'High' | 'Medium' | 'Low' | 'Unresolved';

export type VerificationStatus =
  | 'LOCAL_VERIFIED'
  | 'WEB_RESEARCHED_CANDIDATE'
  | 'VERIFIED_WEB_BACKED'
  | 'UNRESOLVED_UNKNOWN';

export type SourceType =
  | 'government_regulatory'
  | 'official_standards'
  | 'scientific_database'
  | 'peer_reviewed_literature'
  | 'manufacturer_technical'
  | 'reputable_web';

export interface FieldProvenance {
  field: string;
  value: string | number | null;
  sourceUrl?: string;
  sourceTitle?: string;
  sourceType: SourceType;
  retrievedAt: string;
  evidenceText?: string;
  fieldSupported: boolean;
  confidence: number;
  verificationStatus: 'verified' | 'candidate' | 'unresolved';
}

export interface WebResearchSource {
  url: string;
  title: string;
  snippet?: string;
  sourceType: SourceType;
}

export interface WebResearchResult {
  query: string;
  searchedAt: string;
  canonicalName: string;
  aliases: string[];
  identifier: string | null;
  entityType: EntityClassification;
  representationType: RepresentationType;
  chemicalFormula: string | null;
  molecularWeight: number | null;
  casNumber: string | null;
  smiles: string | null;
  chemicalClass: string;
  functionalRole: string;
  summary: string;
  whyUsed: string;
  relevantChemistry: string;
  evidenceSupport: string;
  uncertainties: string;
  isSufficientlyVerified: boolean;
  insufficientEvidenceReason: string | null;
  confidenceLevel: ConfidenceLevel;
  confidenceScore: number;
  verificationStatus: VerificationStatus;
  sources: WebResearchSource[];
  provenance: FieldProvenance[];
  rawSearchQueries?: string[];
}

export type EntityClassification =
  | 'DEFINED_SINGLE_MOLECULE'
  | 'KNOWN_INORGANIC_ENTITY'
  | 'KNOWN_COMPLEX_MIXTURE'
  | 'KNOWN_FORMULATION_COMPONENT'
  | 'AMBIGUOUS'
  | 'UNKNOWN'
  | 'OCR_UNCERTAIN';

export type EvidenceType =
  | 'Regulatory Assessment (EFSA/FDA)'
  | 'Peer-Reviewed Scientific Literature'
  | 'Cosmetic Ingredient Review (CIR)'
  | 'Pharmacopoeia Monograph'
  | 'Chemical Registry (PubChem/CAS)';

export interface Evidence {
  id: string;
  title: string;
  publisher: string;
  url: string;
  evidenceType: EvidenceType;
  accessedAt: string;
  summary: string;
  doiOrRef?: string;
}

export interface ChemicalEntity {
  id: string;
  preferredName: string;
  aliases: string[];
  formula: string | null;
  molecularWeight: number | null;
  cas: string | null;
  smiles: string | null;
  representationType: RepresentationType;
  chemicalClass: string;
  descriptors: string[];
  limitations?: string;
  structureSvgType?: 'sucrose' | 'caffeine' | 'glycerol' | 'citric_acid' | 'sodium_chloride' | 'zinc_oxide' | 'lecithin' | 'none';
}

export interface IngredientRole {
  domain: Domain;
  roleName: string;
  explanation: string;
}

export interface WhyIsThisHere {
  whatIsIt: string;
  whyUsed: string;
  relevantChemistry: string;
  evidenceSupport: string;
  uncertainties: string;
}

export interface ConfidenceBreakdown {
  ocrConfidence: string;
  parsingConfidence: string;
  normalizationConfidence: string;
  entityMatchConfidence: string;
  chemistryConfidence: string;
}

export interface IngredientObservation {
  id: string;
  rawText: string;
  normalizedText: string;
  matchStatus: MatchStatus;
  chemicalEntityId: string | null;
  role: string;
  confidence: ConfidenceLevel;
  confidenceScore: number; // 0 to 100
  evidenceIds: string[];
  whyIsThisHere?: WhyIsThisHere;
  isCustomEdited?: boolean;
  parentId?: string | null;
  depth?: number;
  percentage?: number | null;
  identifier?: string | null;
  classification?: EntityClassification;
  confidenceBreakdown?: ConfidenceBreakdown;
  childrenCount?: number;
  verificationStatus?: VerificationStatus;
  webResearch?: WebResearchResult;
  isResearching?: boolean;
  researchError?: string;
}

export interface IngredientNode {
  id: string;
  rawText: string;
  name: string;
  normalizedName: string;
  percentage: number | null;
  identifier: string | null;
  parentId: string | null;
  position: number;
  depth: number;
  children: IngredientNode[];
  classification: EntityClassification;
  matchStatus: MatchStatus;
  chemicalEntityId: string | null;
  role: string;
  confidence: ConfidenceLevel;
  confidenceScore: number;
  confidenceBreakdown: ConfidenceBreakdown;
  evidenceIds: string[];
  whyIsThisHere?: WhyIsThisHere;
  isCustomEdited?: boolean;
  verificationStatus?: VerificationStatus;
  webResearch?: WebResearchResult;
  isResearching?: boolean;
  researchError?: string;
}

export interface Product {
  id: string;
  name: string;
  brand: string;
  domain: Domain;
  labelText: string;
  imageUrl?: string;
  ingredients: IngredientObservation[];
  ingredientsTree?: IngredientNode[];
  notes?: string;
}

export interface OcrIngredientCandidate {
  raw_text: string;
  position: number;
}

export interface OcrResponse {
  raw_ocr_text: string;
  ingredients: OcrIngredientCandidate[];
  warnings: string[];
  ocr_confidence: string;
}
