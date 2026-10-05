import { Product, IngredientObservation } from '../types';
import { processIngredientsPipeline } from '../lib/pipeline';

const peanutBarParsed = processIngredientsPipeline(
  'Peanut Butter (83%) (Peanut (68%), Jaggery Powder (14%), Stabilizer (INS471), Salt), Whey Protein Concentrate (10%), Dark Chocolate (7%) (Cocoa Powder, Cocoa Butter, Natural Flavouring)',
  'Food',
  'High'
);

export const DEMO_PRODUCTS: Product[] = [
  {
    id: 'prod_peanut_butter_bar',
    name: 'Peanut Butter & Dark Chocolate Protein Slab',
    brand: 'NutriMatrix Kinetics',
    domain: 'Food',
    labelText: 'Peanut Butter (83%) (Peanut (68%), Jaggery Powder (14%), Stabilizer (INS471), Salt), Whey Protein Concentrate (10%), Dark Chocolate (7%) (Cocoa Powder, Cocoa Butter, Natural Flavouring)',
    notes: 'Demonstration of parentheses-aware hierarchy: 3 primary components with 7 nested sub-ingredients, percentages, and additive codes.',
    ingredientsTree: peanutBarParsed.tree,
    ingredients: peanutBarParsed.flattened,
  },
  {
    id: 'prod_cocoa_spread',
    name: 'Artisanal Hazelnut Cocoa Spread',
    brand: 'Nocciola Botanics',
    domain: 'Food',
    labelText: 'Cocoa powder, Sugar, Whey powder, Emulsifer, Salt, Natural flavouring',
    notes: 'Demo label with intentional OCR typo ("Emulsifer") and unresolved botanical mixture ("Natural flavouring").',
    ingredients: [
      {
        id: 'ing_cocoa',
        rawText: 'Cocoa powder',
        normalizedText: 'Cocoa powder',
        matchStatus: 'Matched',
        chemicalEntityId: 'entity_cocoa_powder',
        role: 'Flavoring & Primary Food Base',
        confidence: 'High',
        confidenceScore: 98,
        evidenceIds: ['ev_fao_cocoa'],
        whyIsThisHere: {
          whatIsIt: 'Dry solids obtained by defatting crushed fermented roasted seeds of Theobroma cacao.',
          whyUsed: 'Provides the characteristic chocolate flavor, natural brown color, and structural dry suspension in the lipid continuous phase.',
          relevantChemistry: 'Rich in methylxanthines (theobromine, caffeine) and flavan-3-ol polyphenols. Particle size distribution affects rheological mouthfeel and yield stress in fatty spreads.',
          evidenceSupport: 'Codex Standard for Cocoa Powders (CXS 105-1981) specifies compositional standards for fat, ash, and moisture.',
          uncertainties: 'Alkalization (Dutch processing) status is not stated on label; alkalization alters polyphenol content and pH from ~5.5 to >7.0.'
        }
      },
      {
        id: 'ing_sugar',
        rawText: 'Sugar',
        normalizedText: 'Sugar (Sucrose)',
        matchStatus: 'Matched',
        chemicalEntityId: 'entity_sucrose',
        role: 'Bulking Sweetener & Texture Agent',
        confidence: 'High',
        confidenceScore: 99,
        evidenceIds: ['ev_efsa_sucrose'],
        whyIsThisHere: {
          whatIsIt: 'Purified crystalline non-reducing disaccharide composed of glucose and fructose bonded by an α-(1→2)-β glycosidic linkage.',
          whyUsed: 'Balances natural bitterness of cocoa and creates particulate body in spread matrix.',
          relevantChemistry: 'High thermodynamic solubility in moisture, but in lipid-continuous confectionery spreads it exists as dispersed solid crystals. Crystal size (<30 µm) governs grittiness perception.',
          evidenceSupport: 'EFSA Scientific Opinion on Dietary Sugars (2022) describes metabolic fate and technological crystallization behavior.',
          uncertainties: 'Botanical source (sugar beet Beta vulgaris vs sugarcane Saccharum officinarum) is chemically indistinguishable once refined to >=99.8% purity.'
        }
      },
      {
        id: 'ing_whey',
        rawText: 'Whey powder',
        normalizedText: 'Whey powder',
        matchStatus: 'Matched',
        chemicalEntityId: 'entity_whey_powder',
        role: 'Bulking Agent & Dairy Solids',
        confidence: 'High',
        confidenceScore: 95,
        evidenceIds: ['ev_fao_cocoa'],
        whyIsThisHere: {
          whatIsIt: 'Spray-dried serum co-product of cheese manufacture, containing globular milk proteins (β-lactoglobulin, α-lactalbumin) and lactose.',
          whyUsed: 'Provides dairy mouthfeel, partial emulsification assistance, and cost-effective solids replacement without excessive sweetening.',
          relevantChemistry: 'Contains amphiphilic globular proteins that unfold at lipid-water interfaces, stabilizing secondary dispersed moisture droplets.',
          evidenceSupport: 'Codex Alimentarius standards for dairy powders and cheese whey fractions.',
          uncertainties: 'Demineralization level and native mineral salt concentration (calcium, phosphates) vary by dairy processing plant.'
        }
      },
      {
        id: 'ing_emulsifier',
        rawText: 'Emulsifer', // Intentional OCR typo!
        normalizedText: 'Emulsifier (Likely typo: corrected to Lecithin)',
        matchStatus: 'Partially matched',
        chemicalEntityId: 'entity_lecithin',
        role: 'Interfacial Surfactant & Viscosity Reducer',
        confidence: 'Medium',
        confidenceScore: 78,
        evidenceIds: ['ev_fda_lecithin'],
        whyIsThisHere: {
          whatIsIt: 'Surface-active lipid compound, commonly soy or sunflower phospholipid complex containing phosphatidylcholine and phosphatidylethanolamine.',
          whyUsed: 'Reduces plastic viscosity and Casson yield stress in lipid-continuous confectionery matrices by coating solid sugar and cocoa particles.',
          relevantChemistry: 'Zwitterionic polar head groups adsorb to hydrophilic sugar crystals while non-polar fatty acyl tails extend into continuous vegetable oil phase.',
          evidenceSupport: 'FDA 21 CFR §184.1400 affirms lecithin GRAS status for lowering interfacial tension and modifying crystallization kinetics.',
          uncertainties: 'The raw label text contains an OCR spelling defect ("Emulsifer") and lacks specific botanical origin (e.g. soy vs sunflower vs PGPR synthetic polyglycerol polyricinoleate).'
        }
      },
      {
        id: 'ing_salt',
        rawText: 'Salt',
        normalizedText: 'Salt (Sodium Chloride)',
        matchStatus: 'Matched',
        chemicalEntityId: 'entity_sodium_chloride',
        role: 'Flavor Modulator & Water Activity Depressant',
        confidence: 'High',
        confidenceScore: 99,
        evidenceIds: ['ev_codex_salt'],
        whyIsThisHere: {
          whatIsIt: 'Inorganic ionic compound consisting of a 1:1 stoichiometric ratio of sodium cations and chloride anions arranged in an FCC crystal lattice.',
          whyUsed: 'Suppresses perceived bitterness in cocoa solids, enhances sweetness perception via taste receptor T1R2/T1R3 modulation, and binds residual moisture.',
          relevantChemistry: 'High ionic dissociation energy. In the presence of micro-moisture pockets, creates high localized osmotic pressure.',
          evidenceSupport: 'Codex Standard for Food Grade Salt (CXS 150-1985).',
          uncertainties: 'Presence or absence of anti-caking additives (such as sodium ferrocyanide or silicon dioxide) is not declared on label.'
        }
      },
      {
        id: 'ing_natural_flavour',
        rawText: 'Natural flavouring',
        normalizedText: 'Natural flavouring',
        matchStatus: 'Unknown',
        chemicalEntityId: null, // Deliberately unresolved!
        role: 'Aroma & Sensory Modifier',
        confidence: 'Unresolved',
        confidenceScore: 35,
        evidenceIds: ['ev_efsa_flavouring_uncertainty'],
        whyIsThisHere: {
          whatIsIt: 'Umbrella regulatory designation for volatile aromatic compounds obtained by physical, enzymatic, or microbiological processes from vegetal or animal materials.',
          whyUsed: 'Imparts specific top-note sensory attributes (e.g., roasted hazelnut notes, vanilla aromatics) lost during thermal industrial pasteurization.',
          relevantChemistry: 'Typically an undefined cocktail of volatile aldehydes, esters, terpenes, or pyrazines dissolved in an edible solvent carrier (e.g. triacetin, propylene glycol, or plant oil).',
          evidenceSupport: 'EFSA CEF Guidance (2010) on Flavouring Substances specifies that umbrella terms represent complex multi-constituent mixtures rather than identifiable chemical isolates.',
          uncertainties: 'Not confidently resolved to a single chemical entity. The chemical identity, solvent carrier, concentration, and molecular composition cannot be determined from the ingredient statement alone. Do not invent a molecular structure for it.'
        }
      }
    ]
  },

  {
    id: 'prod_cocoa_spread_organic',
    name: 'Organic Dark Hazelnut Spread',
    brand: 'Verdant Earth Co.',
    domain: 'Food',
    labelText: 'Cocoa powder, Cane sugar, Hazelnuts (18%), Sunflower lecithin, Sea salt, Vanilla extract',
    notes: 'Comparative product with explicitly stated lecithin source and botanical nut fraction.',
    ingredients: [
      {
        id: 'ing_cocoa_org',
        rawText: 'Cocoa powder',
        normalizedText: 'Cocoa powder',
        matchStatus: 'Matched',
        chemicalEntityId: 'entity_cocoa_powder',
        role: 'Flavoring & Primary Food Base',
        confidence: 'High',
        confidenceScore: 98,
        evidenceIds: ['ev_fao_cocoa'],
        whyIsThisHere: {
          whatIsIt: 'Organic dry cocoa solids from roasted Theobroma cacao beans.',
          whyUsed: 'Provides deep chocolate flavor base and polyphenol content.',
          relevantChemistry: 'Non-fat solids containing theobromine and proanthocyanidins.',
          evidenceSupport: 'Codex Standard CXS 105-1981.',
          uncertainties: 'Exact bean provenance and roast intensity curve are proprietary.'
        }
      },
      {
        id: 'ing_cane_sugar',
        rawText: 'Cane sugar',
        normalizedText: 'Sugar (Sucrose)',
        matchStatus: 'Matched',
        chemicalEntityId: 'entity_sucrose',
        role: 'Bulking Sweetener',
        confidence: 'High',
        confidenceScore: 99,
        evidenceIds: ['ev_efsa_sucrose'],
        whyIsThisHere: {
          whatIsIt: 'Crystalline sucrose extracted from sugarcane (Saccharum officinarum).',
          whyUsed: 'Sweetener and crystalline structuring agent.',
          relevantChemistry: 'Identical disaccharide molecular structure (C12H22O11) to beet sucrose.',
          evidenceSupport: 'EFSA Scientific Opinion on Dietary Sugars (2022).',
          uncertainties: 'Trace inverted sugars (<0.1%) present in unbleached cane crystals.'
        }
      },
      {
        id: 'ing_sunflower_lecithin',
        rawText: 'Sunflower lecithin',
        normalizedText: 'Lecithin (Sunflower-derived)',
        matchStatus: 'Matched',
        chemicalEntityId: 'entity_lecithin',
        role: 'Interfacial Emulsifier',
        confidence: 'High',
        confidenceScore: 96,
        evidenceIds: ['ev_fda_lecithin'],
        whyIsThisHere: {
          whatIsIt: 'Non-GMO phospholipid fraction cold-pressed from Helianthus annuus seeds.',
          whyUsed: 'Lowers chocolate paste yield value without introducing soy allergen liabilities.',
          relevantChemistry: 'Mixture of phosphatidylcholine, phosphatidylethanolamine, and phosphatidylinositol.',
          evidenceSupport: 'FDA 21 CFR §184.1400 (GRAS affirms lecithin).',
          uncertainties: 'Phospholipid species ratio fluctuates naturally across agricultural sunflower harvests.'
        }
      },
      {
        id: 'ing_sea_salt',
        rawText: 'Sea salt',
        normalizedText: 'Sodium Chloride (Marine origin)',
        matchStatus: 'Matched',
        chemicalEntityId: 'entity_sodium_chloride',
        role: 'Flavor Modulator & Osmotic Agent',
        confidence: 'High',
        confidenceScore: 98,
        evidenceIds: ['ev_codex_salt'],
        whyIsThisHere: {
          whatIsIt: 'Sodium chloride harvested via evaporation of seawater.',
          whyUsed: 'Flavor modulation and suppression of perceived bitter tannin notes.',
          relevantChemistry: '>=98% ionic NaCl crystal lattice with trace marine magnesium and sulfate ions.',
          evidenceSupport: 'Codex Standard for Food Grade Salt (CXS 150-1985).',
          uncertainties: 'Trace mineral fractions (<0.5%) depend on evaporation basin geography.'
        }
      }
    ]
  },

  {
    id: 'prod_oat_latte',
    name: 'Barista Edition Oat Milk',
    brand: 'Nordic Grain Lab',
    domain: 'Beverage',
    labelText: 'Water, Oat base (water, oats 10%), Rapeseed oil, Dipotassium phosphate, Calcium carbonate, Sea salt',
    notes: 'Technical formulation engineered for microfoam aeration and coffee acidity buffering.',
    ingredients: [
      {
        id: 'ing_oat_base',
        rawText: 'Oat base (water, oats 10%)',
        normalizedText: 'Oat Base / Extract',
        matchStatus: 'Matched',
        chemicalEntityId: 'entity_oat_base',
        role: 'Liquid Continuous Base & Carbohydrate Source',
        confidence: 'High',
        confidenceScore: 94,
        evidenceIds: ['ev_efsa_flavouring_uncertainty'],
        whyIsThisHere: {
          whatIsIt: 'Aqueous suspension produced by enzymatic hydrolysis of whole grain oats using food-grade amylases.',
          whyUsed: 'Delivers soluble oat dietary fibers (β-glucans), natural sweetness, and creaminess without dairy.',
          relevantChemistry: 'Hydrolysis converts long insoluble starch chains into shorter maltodextrins and maltose while retaining high-viscosity soluble β-glucan.',
          evidenceSupport: 'Peer-reviewed food chemistry literature on cereal enzymology.',
          uncertainties: 'Enzymatic degree of hydrolysis (DE) is undisclosed.'
        }
      },
      {
        id: 'ing_dipotassium_phosphate',
        rawText: 'Dipotassium phosphate',
        normalizedText: 'Dipotassium Phosphate (E 340ii)',
        matchStatus: 'Matched',
        chemicalEntityId: 'entity_dipotassium_phosphate',
        role: 'Acidity Regulator & Protein Thermal Stabilizer',
        confidence: 'High',
        confidenceScore: 98,
        evidenceIds: ['ev_efsa_citric_acid'],
        whyIsThisHere: {
          whatIsIt: 'Inorganic salt of potassium and monohydrogen phosphate (K2HPO4).',
          whyUsed: 'Crucial in barista beverages: prevents the plant proteins from curdling/feathering when poured into acidic hot espresso (pH ~4.8–5.2).',
          relevantChemistry: 'Acts as a buffer resisting pH drop and chelates divalent metal ions that could trigger rapid protein flocculation.',
          evidenceSupport: 'EFSA and Codex food additive evaluations on phosphates.',
          uncertainties: 'Specific phosphate concentration in finished beverage.'
        }
      },
      {
        id: 'ing_sea_salt_oat',
        rawText: 'Sea salt',
        normalizedText: 'Sodium Chloride',
        matchStatus: 'Matched',
        chemicalEntityId: 'entity_sodium_chloride',
        role: 'Electrolyte & Taste Modulator',
        confidence: 'High',
        confidenceScore: 98,
        evidenceIds: ['ev_codex_salt'],
        whyIsThisHere: {
          whatIsIt: 'Refined marine sodium chloride.',
          whyUsed: 'Elevates perceived sweetness of hydrolyzed oat sugars via sodium-glucose cotransporter affinity.',
          relevantChemistry: 'Ionic dissolution into Na⁺ and Cl⁻ ions.',
          evidenceSupport: 'Codex Standard CXS 150-1985.',
          uncertainties: 'None; simple inorganic salt.'
        }
      }
    ]
  },

  {
    id: 'prod_cleanser_gel',
    name: 'Gentle Hydrating Cleansing Gel',
    brand: 'DermaMatrix Labs',
    domain: 'Cosmetics',
    labelText: 'Aqua (Water), Glycerin, Coco-Glucoside, Citric Acid, Xanthan Gum',
    notes: 'Minimalist pH-balanced facial cleanser showcasing humectants, mild non-ionic surfactants, and rheology modifiers.',
    ingredients: [
      {
        id: 'ing_glycerin_derm',
        rawText: 'Glycerin',
        normalizedText: 'Glycerol',
        matchStatus: 'Matched',
        chemicalEntityId: 'entity_glycerol',
        role: 'Humectant & Skin Conditioning Agent',
        confidence: 'High',
        confidenceScore: 99,
        evidenceIds: ['ev_cir_glycerin'],
        whyIsThisHere: {
          whatIsIt: 'Simple polyol compound consisting of a propane backbone with three hydroxyl groups.',
          whyUsed: 'Maintains skin hydration during surfactant contact, attenuating trans-epidermal water loss (TEWL).',
          relevantChemistry: 'Forms extensive hydrogen-bonding networks with water molecules, holding moisture within stratum corneum lipids.',
          evidenceSupport: 'CIR Safety Assessment confirms high tolerability and humectant efficacy.',
          uncertainties: 'Concentration level in formulation (typical range 2%–10%).'
        }
      },
      {
        id: 'ing_coco_glucoside',
        rawText: 'Coco-Glucoside',
        normalizedText: 'Coco-Glucoside',
        matchStatus: 'Matched',
        chemicalEntityId: 'entity_coco_glucoside',
        role: 'Primary Non-Ionic Surfactant / Cleanser',
        confidence: 'High',
        confidenceScore: 96,
        evidenceIds: ['ev_cir_glycerin'],
        whyIsThisHere: {
          whatIsIt: 'Alkyl polyglucoside synthesized by reacting glucose with coconut-derived fatty alcohols.',
          whyUsed: 'Gently cleanses sebum without aggressively denaturing skin keratin or disrupting barrier lipids.',
          relevantChemistry: 'Bulky hydrophilic glucose head prevents aggressive penetration into stratum corneum lipid bilayers compared to anionic sulfates.',
          evidenceSupport: 'CIR safety report on alkyl glucosides.',
          uncertainties: 'Fatty alcohol chain distribution (C8 to C16 blend).'
        }
      },
      {
        id: 'ing_citric_acid_cosm',
        rawText: 'Citric Acid',
        normalizedText: 'Citric Acid',
        matchStatus: 'Matched',
        chemicalEntityId: 'entity_citric_acid',
        role: 'pH Adjuster & Buffer',
        confidence: 'High',
        confidenceScore: 99,
        evidenceIds: ['ev_efsa_citric_acid'],
        whyIsThisHere: {
          whatIsIt: 'Tricarboxylic organic acid (pKa1=3.13).',
          whyUsed: 'Acidifies formula to match the physiological skin acid mantle (pH ~5.0–5.5).',
          relevantChemistry: 'Triprotic buffering system that also sequesters trace water-borne metal ions.',
          evidenceSupport: 'CIR Cosmetic Ingredient Review Panel safety evaluation of alpha hydroxy acids.',
          uncertainties: 'Exact pH endpoint of the unbuffered batch.'
        }
      },
      {
        id: 'ing_xanthan_gum',
        rawText: 'Xanthan Gum',
        normalizedText: 'Xanthan Gum',
        matchStatus: 'Matched',
        chemicalEntityId: 'entity_xanthan_gum',
        role: 'Viscosity Builder & Rheology Modifier',
        confidence: 'High',
        confidenceScore: 97,
        evidenceIds: ['ev_cir_glycerin'],
        whyIsThisHere: {
          whatIsIt: 'High-molecular-weight microbial polysaccharide produced by Xanthomonas campestris.',
          whyUsed: 'Provides pleasant gel structure that suspends surfactant micelles and thins under shear during face washing.',
          relevantChemistry: 'Forms rigid polymer networks in water that exhibit pseudoplastic shear-thinning behavior.',
          evidenceSupport: 'CIR Safety Assessment of Microbial Polysaccharide Gums.',
          uncertainties: 'Polymer molecular weight distribution across commercial grades.'
        }
      }
    ]
  },

  {
    id: 'prod_mineral_sunscreen',
    name: 'Broad Spectrum Mineral Sunscreen SPF 30',
    brand: 'Solaris Pure Chemistry',
    domain: 'Personal Care',
    labelText: 'Zinc Oxide (18.5%), Aqua, Caprylic/Capric Triglyceride, Glycerin, Polyglyceryl-3 Polyricinoleate',
    notes: 'Physical inorganic UV filter formulation with water-in-oil emulsion architecture.',
    ingredients: [
      {
        id: 'ing_zinc_oxide',
        rawText: 'Zinc Oxide (18.5%)',
        normalizedText: 'Zinc Oxide',
        matchStatus: 'Matched',
        chemicalEntityId: 'entity_zinc_oxide',
        role: 'Physical UV-A / UV-B Sunscreen Active Filter',
        confidence: 'High',
        confidenceScore: 99,
        evidenceIds: ['ev_fda_zinc_oxide'],
        whyIsThisHere: {
          whatIsIt: 'Inorganic mineral oxide with a hexagonal wurtzite crystal structure.',
          whyUsed: 'Provides broad-spectrum photoprotection by reflecting, scattering, and absorbing harmful UV-A (320–400 nm) and UV-B (290–320 nm) photons.',
          relevantChemistry: 'Wide bandgap (~3.37 eV) semiconductor. Photon absorption excites electrons across bandgap, converting UV energy safely into low-level thermal vibration.',
          evidenceSupport: 'FDA OTC Sunscreen Monograph M020 classifies zinc oxide up to 25% as Category I GRASE.',
          uncertainties: 'Surface silane/stearate coating chemistry and mean primary particle diameter are proprietary.'
        }
      },
      {
        id: 'ing_glycerin_sun',
        rawText: 'Glycerin',
        normalizedText: 'Glycerol',
        matchStatus: 'Matched',
        chemicalEntityId: 'entity_glycerol',
        role: 'Humectant & Freeze-Thaw Stabilizer',
        confidence: 'High',
        confidenceScore: 99,
        evidenceIds: ['ev_cir_glycerin'],
        whyIsThisHere: {
          whatIsIt: 'Trihydroxy alcohol (propane-1,2,3-triol).',
          whyUsed: 'Supplements hydration in the internal aqueous phase of water-in-oil sunscreens.',
          relevantChemistry: 'Depresses freezing point of internal water droplets, preventing crystal disruption of the surfactant film.',
          evidenceSupport: 'CIR safety monograph on glycerol in cosmetics.',
          uncertainties: 'None.'
        }
      }
    ]
  }
];
