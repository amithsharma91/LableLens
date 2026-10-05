/**
 * Generates authentic, high-contrast label image data URLs for demo products.
 * Includes barcode graphics, regulatory boxes, and the printed ingredient statement.
 */

function createSvgLabelDataUrl(params: {
  brand: string;
  productName: string;
  category: string;
  ingredientsText: string;
  extraInfo?: string;
  hasTypoNotice?: boolean;
}): string {
  const { brand, productName, category, ingredientsText, extraInfo, hasTypoNotice } = params;

  // Render a crisp packaging label
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="800" height="520" viewBox="0 0 800 520">
    <defs>
      <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#fdfdfd" />
        <stop offset="100%" stop-color="#f4f5f7" />
      </linearGradient>
      <filter id="shadow" x="-5%" y="-5%" width="110%" height="110%">
        <feDropShadow dx="0" dy="4" stdDeviation="6" flood-color="#0f172a" flood-opacity="0.08" />
      </filter>
    </defs>

    <!-- Label Border & Surface -->
    <rect x="20" y="20" width="760" height="480" rx="16" fill="url(#bg)" stroke="#cbd5e1" stroke-width="2" filter="url(#shadow)" />
    
    <!-- Top Branding Strip -->
    <rect x="20" y="20" width="760" height="70" rx="16" fill="#0f172a" />
    <text x="50" y="62" font-family="'Helvetica Neue', Arial, sans-serif" font-size="22" font-weight="bold" fill="#ffffff" letter-spacing="3">${brand.toUpperCase()}</text>
    <text x="730" y="62" font-family="monospace" font-size="12" fill="#94a3b8" text-anchor="end" letter-spacing="1">AUTHENTIC PACKAGING SAMPLE</text>

    <!-- Product Title -->
    <text x="50" y="130" font-family="'Helvetica Neue', Arial, sans-serif" font-size="26" font-weight="bold" fill="#1e293b">${productName}</text>
    <text x="50" y="155" font-family="'Helvetica Neue', Arial, sans-serif" font-size="14" font-weight="600" fill="#64748b" letter-spacing="1.5">${category.toUpperCase()} SPECIFICATION</text>

    <!-- Ingredients Container -->
    <rect x="50" y="180" width="700" height="170" rx="10" fill="#ffffff" stroke="#94a3b8" stroke-width="1.5" />
    
    <text x="70" y="215" font-family="'Helvetica Neue', Arial, sans-serif" font-size="14" font-weight="bold" fill="#0f172a" letter-spacing="1.5">INGREDIENTS STATEMENT / COMPOSITION:</text>
    
    <!-- Word-wrapped ingredients block -->
    <foreignObject x="70" y="230" width="660" height="100">
      <div xmlns="http://www.w3.org/1999/xhtml" style="font-family: 'Helvetica Neue', Arial, sans-serif; font-size: 16px; font-weight: 500; line-height: 1.6; color: #1e293b;">
        ${ingredientsText}
      </div>
    </foreignObject>

    <!-- Regulatory & Barcode Box -->
    <rect x="50" y="370" width="450" height="100" rx="8" fill="#f8fafc" stroke="#e2e8f0" stroke-width="1" />
    <text x="70" y="400" font-family="'Helvetica Neue', Arial, sans-serif" font-size="12" font-weight="bold" fill="#475569">STORAGE & USAGE INSTRUCTIONS:</text>
    <text x="70" y="425" font-family="'Helvetica Neue', Arial, sans-serif" font-size="11" fill="#64748b">Store in a cool, dry place. Keep away from direct sunlight.</text>
    <text x="70" y="445" font-family="monospace" font-size="10" fill="#94a3b8">${extraInfo || 'BATCH NO: LL-2026-X99 · NET WT: 350g e'}</text>

    <!-- Barcode simulation -->
    <g transform="translate(530, 375)">
      <rect x="0" y="0" width="220" height="90" rx="6" fill="#ffffff" stroke="#cbd5e1" stroke-width="1" />
      <!-- Barcode lines -->
      <line x1="20" y1="15" x2="20" y2="65" stroke="#000" stroke-width="3" />
      <line x1="27" y1="15" x2="27" y2="65" stroke="#000" stroke-width="1" />
      <line x1="33" y1="15" x2="33" y2="65" stroke="#000" stroke-width="4" />
      <line x1="42" y1="15" x2="42" y2="65" stroke="#000" stroke-width="2" />
      <line x1="50" y1="15" x2="50" y2="65" stroke="#000" stroke-width="1" />
      <line x1="56" y1="15" x2="56" y2="65" stroke="#000" stroke-width="3" />
      <line x1="65" y1="15" x2="65" y2="65" stroke="#000" stroke-width="2" />
      <line x1="72" y1="15" x2="72" y2="65" stroke="#000" stroke-width="4" />
      <line x1="82" y1="15" x2="82" y2="65" stroke="#000" stroke-width="1" />
      <line x1="90" y1="15" x2="90" y2="65" stroke="#000" stroke-width="3" />
      <line x1="100" y1="15" x2="100" y2="65" stroke="#000" stroke-width="2" />
      <line x1="110" y1="15" x2="110" y2="65" stroke="#000" stroke-width="4" />
      <line x1="120" y1="15" x2="120" y2="65" stroke="#000" stroke-width="1" />
      <line x1="130" y1="15" x2="130" y2="65" stroke="#000" stroke-width="3" />
      <line x1="140" y1="15" x2="140" y2="65" stroke="#000" stroke-width="2" />
      <line x1="150" y1="15" x2="150" y2="65" stroke="#000" stroke-width="3" />
      <line x1="160" y1="15" x2="160" y2="65" stroke="#000" stroke-width="1" />
      <line x1="170" y1="15" x2="170" y2="65" stroke="#000" stroke-width="4" />
      <line x1="180" y1="15" x2="180" y2="65" stroke="#000" stroke-width="2" />
      <line x1="190" y1="15" x2="190" y2="65" stroke="#000" stroke-width="3" />
      <text x="105" y="80" font-family="monospace" font-size="11" fill="#334155" text-anchor="middle">5 901234 567890</text>
    </g>
  </svg>`;

  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

export const DEMO_PRODUCT_IMAGES: Record<string, string> = {
  // Scenario from prompt: Nested ingredient statement with percentages and additive codes
  prod_peanut_butter_bar: createSvgLabelDataUrl({
    brand: 'NutriMatrix Kinetics',
    productName: 'Peanut Butter & Dark Chocolate Protein Slab',
    category: 'High-Protein Functional Food',
    ingredientsText: 'INGREDIENTS: Peanut Butter (83%) (Peanut (68%), Jaggery Powder (14%), Stabilizer (INS471), Salt), Whey Protein Concentrate (10%), Dark Chocolate (7%) (Cocoa Powder, Cocoa Butter, Natural Flavouring).',
    extraInfo: '3 PRIMARY COMPONENTS · 7 NESTED SUB-INGREDIENTS · NET WT: 65g',
  }),

  // Contains the printed typo "Emulsifer" as required by the prompt
  prod_cocoa_spread: createSvgLabelDataUrl({
    brand: 'Nocciola Botanics',
    productName: 'Artisanal Hazelnut Cocoa Spread',
    category: 'Food Packaging Label',
    ingredientsText: 'INGREDIENTS: Cocoa powder, Sugar, Whey powder, Emulsifer, Salt, Natural flavouring.',
    extraInfo: 'LOT: NB-7729 · NET WEIGHT: 350g e · PACKAGED IN GLASS',
    hasTypoNotice: true,
  }),

  prod_cocoa_spread_organic: createSvgLabelDataUrl({
    brand: 'Verdant Earth Co.',
    productName: 'Organic Dark Hazelnut Spread',
    category: 'Organic Food Product',
    ingredientsText: 'INGREDIENTS: Cocoa powder, Cane sugar, Hazelnuts (18%), Sunflower lecithin, Sea salt, Vanilla extract.',
    extraInfo: 'CERTIFIED ORGANIC · NET WT: 300g',
  }),

  prod_oat_latte: createSvgLabelDataUrl({
    brand: 'Nordic Grain Lab',
    productName: 'Barista Edition Oat Milk',
    category: 'Plant-Based Beverage Cartons',
    ingredientsText: 'INGREDIENTS: Water, Oat base (water, oats 10%), Rapeseed oil, Dipotassium phosphate, Calcium carbonate, Sea salt.',
    extraInfo: 'KEEP REFRIGERATED · 1000 mL (1 LITRE)',
  }),

  prod_cleanser_gel: createSvgLabelDataUrl({
    brand: 'DermaMatrix Labs',
    productName: 'Gentle Hydrating Cleansing Gel',
    category: 'Dermatological Cosmetic Formulation',
    ingredientsText: 'INGREDIENTS: Aqua (Water), Glycerin, Coco-Glucoside, Citric Acid, Xanthan Gum.',
    extraInfo: 'pH 5.5 · 150 mL / 5.1 FL. OZ.',
  }),

  prod_mineral_sunscreen: createSvgLabelDataUrl({
    brand: 'Solaris Pure Chemistry',
    productName: 'Broad Spectrum Mineral Sunscreen SPF 30',
    category: 'Personal Care Drug Monograph',
    ingredientsText: 'ACTIVE INGREDIENT: Zinc Oxide (18.5%). INACTIVE INGREDIENTS: Aqua, Caprylic/Capric Triglyceride, Glycerin, Polyglyceryl-3 Polyricinoleate.',
    extraInfo: 'BROAD SPECTRUM SPF 30 · WATER RESISTANT (80 MIN) · 100 mL',
  }),
};
