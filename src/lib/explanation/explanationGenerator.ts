import { ChemicalEntity, Domain, EntityClassification, WhyIsThisHere } from '../../types';

export function generateWhyIsThisHereExplanation(params: {
  ingredientName: string;
  classification: EntityClassification;
  entity: ChemicalEntity | null;
  role: string;
  domain: Domain;
  identifier: string | null;
  evidenceIds: string[];
  hasChildren: boolean;
}): WhyIsThisHere {
  const { ingredientName, classification, entity, role, domain, identifier, evidenceIds, hasChildren } = params;

  // 1. Unresolved or Ambiguous Ingredients
  if (classification === 'AMBIGUOUS' || classification === 'UNKNOWN') {
    return {
      whatIsIt: `Unresolved packaging declaration ("${ingredientName}").`,
      whyUsed: 'Role not confidently resolved from label text alone.',
      relevantChemistry: 'Chemical identity, constituent molecules, and carrier matrices are undisclosed on packaging.',
      evidenceSupport: 'Statutory labeling frameworks (e.g. EFSA, US FDA) permit composite umbrella terms without chemical speciation.',
      uncertainties: 'Not confidently resolved to a single chemical entity. The chemical identity, solvent carrier, concentration, and molecular composition cannot be determined from the ingredient statement alone. Do not invent a molecular structure for it.',
    };
  }

  // 2. Parent Formulations (Peanut Butter, Dark Chocolate, Compound Chocolate)
  if (hasChildren || classification === 'KNOWN_FORMULATION_COMPONENT') {
    return {
      whatIsIt: `${ingredientName} is a composite formulated food component comprising multiple sub-ingredients.`,
      whyUsed: `Provides the primary organoleptic body, texture, and core matrix in this ${domain.toLowerCase()} formulation.`,
      relevantChemistry: 'Continuous multiphase suspension (lipids, carbohydrates, and proteins). Physical properties depend on the shear and crystallization of its declared sub-ingredients.',
      evidenceSupport: evidenceIds.length > 0 ? `Codex Alimentarius standards and commercial food specification monographs.` : 'Declared in compliance with ingredient compound labeling regulations.',
      uncertainties: 'Rheological mouthfeel and phase stability vary with processing temperature and particle size distribution.',
    };
  }

  // 3. Additive codes (e.g. INS 471, INS 322)
  if (identifier && entity) {
    return {
      whatIsIt: `${entity.preferredName} (${identifier}) is a technological food additive.`,
      whyUsed: `Functions as an ${role.toLowerCase()} to prevent phase separation and stabilize the lipid matrix.`,
      relevantChemistry: entity.descriptors.join('. ') + '.',
      evidenceSupport: evidenceIds.length > 0 ? `Codex General Standard for Food Additives (GSFA) and EFSA re-evaluations.` : 'International Numbering System (INS) statutory additive approval.',
      uncertainties: entity.limitations || 'Exact fatty acid chain length and commercial mono/diglyceride ratio are manufacturer-dependent.',
    };
  }

  // 4. Known single molecules (Sucrose, Citric Acid, Caffeine, Glycerol)
  if (classification === 'DEFINED_SINGLE_MOLECULE' && entity) {
    return {
      whatIsIt: `${entity.preferredName} (${entity.formula}, MW ${entity.molecularWeight} g/mol) is a defined chemical substance.`,
      whyUsed: `Utilized as ${role.toLowerCase()} in this ${domain.toLowerCase()} formulation.`,
      relevantChemistry: entity.descriptors.join('. ') + '.',
      evidenceSupport: `Documented in authoritative literature (${evidenceIds.join(', ')}).`,
      uncertainties: entity.limitations || 'Purity and physical crystal grade remain proprietary to supplier.',
    };
  }

  // 5. Known inorganic minerals (Salt, Zinc Oxide, Dipotassium Phosphate)
  if (classification === 'KNOWN_INORGANIC_ENTITY' && entity) {
    return {
      whatIsIt: `${entity.preferredName} (${entity.formula}) is an inorganic mineral entity with an empirical crystal lattice.`,
      whyUsed: `Acts as ${role.toLowerCase()} to optimize osmotic balance and taste receptor response.`,
      relevantChemistry: entity.descriptors.join('. ') + '.',
      evidenceSupport: `Codex Alimentarius and national food monographs (${evidenceIds.join(', ')}).`,
      uncertainties: entity.limitations || 'None.',
    };
  }

  // 6. Known complex materials (Peanut, Jaggery, Whey Protein, Cocoa Powder, Cocoa Butter)
  if (classification === 'KNOWN_COMPLEX_MIXTURE' && entity) {
    return {
      whatIsIt: `${entity.preferredName} is a natural agricultural/biological material matrix.`,
      whyUsed: `Provides authentic nutrient density, solids, and functional mouthfeel as ${role.toLowerCase()}.`,
      relevantChemistry: entity.descriptors.join('. ') + '.',
      evidenceSupport: 'Peer-reviewed agricultural food composition databases and commodity standards.',
      uncertainties: entity.limitations || 'Compositional lipids and proteins naturally vary by harvest crop and processing geography.',
    };
  }

  // Fallback
  return {
    whatIsIt: `${ingredientName} is a declared packaging component.`,
    whyUsed: role !== 'Formulation Component' ? `Functions as ${role.toLowerCase()}.` : 'Role not confidently resolved from label text alone.',
    relevantChemistry: 'Not available for this representation.',
    evidenceSupport: evidenceIds.join(', ') || 'Packaging declaration.',
    uncertainties: 'Empirical entity boundaries depend on manufacturing source.',
  };
}
