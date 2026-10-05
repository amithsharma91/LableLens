import React from 'react';
import { Camera, Search, Scale, BookOpen, ArrowRight, ShieldCheck, Microscope, Database, HelpCircle } from 'lucide-react';
import { DEMO_PRODUCTS } from '../data/demoProducts';
import { Product } from '../types';

interface HomeViewProps {
  onStartScan: (presetProduct?: Product) => void;
  onSelectProduct: (product: Product) => void;
  onNavigate: (tab: 'scan' | 'compare' | 'catalog' | 'learn') => void;
}

export const HomeView: React.FC<HomeViewProps> = ({
  onStartScan,
  onSelectProduct,
  onNavigate,
}) => {
  return (
    <div className="space-y-12 pb-16">
      {/* Hero Section */}
      <section className="pt-6 sm:pt-12 pb-6 max-w-4xl mx-auto px-4 text-center">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-slate-100 border border-slate-200 text-xs font-mono text-slate-700 mb-6">
          <span className="w-2 h-2 rounded-full bg-blue-600"></span>
          <span>Computational Product Label Intelligence</span>
        </div>

        <h1 className="text-3xl sm:text-5xl font-bold tracking-tight text-slate-900 leading-[1.15] text-balance">
          Understand what’s inside.
        </h1>

        <p className="mt-4 text-base sm:text-lg text-slate-600 max-w-2xl mx-auto leading-relaxed text-balance">
          Bridging packaging claims with physical chemistry. Transform raw label text into verified chemical entities, 
          molecular structures, and peer-reviewed functional evidence — without moralizing classifications.
        </p>

        {/* Primary and secondary CTAs */}
        <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-3">
          <button
            onClick={() => onStartScan()}
            className="w-full sm:w-auto px-6 py-3 bg-slate-900 hover:bg-slate-800 text-white rounded-xl font-medium text-sm shadow-md hover:shadow-lg transition-all flex items-center justify-center gap-2 active:scale-[0.98] cursor-pointer"
          >
            <Camera className="w-4 h-4" />
            <span>Scan a Label</span>
          </button>

          <button
            onClick={() => onNavigate('catalog')}
            className="w-full sm:w-auto px-5 py-3 bg-white hover:bg-slate-50 border border-slate-300 text-slate-700 rounded-xl font-medium text-sm transition-all flex items-center justify-center gap-2 cursor-pointer"
          >
            <Search className="w-4 h-4 text-slate-500" />
            <span>Search Ingredient</span>
          </button>

          <button
            onClick={() => onNavigate('compare')}
            className="w-full sm:w-auto px-5 py-3 bg-white hover:bg-slate-50 border border-slate-300 text-slate-700 rounded-xl font-medium text-sm transition-all flex items-center justify-center gap-2 cursor-pointer"
          >
            <Scale className="w-4 h-4 text-slate-500" />
            <span>Compare Products</span>
          </button>
        </div>

        {/* Pipeline steps */}
        <div className="mt-12 pt-8 border-t border-slate-200 grid grid-cols-2 md:grid-cols-4 gap-4 text-left">
          <div className="p-3 bg-white rounded-lg border border-slate-200 shadow-xs">
            <span className="text-[11px] font-mono text-slate-600">01. INGESTION</span>
            <h4 className="text-sm font-semibold text-slate-900 mt-1">Label OCR</h4>
            <p className="text-xs text-slate-500 mt-0.5">Segment raw packaging text into editable ingredient strings.</p>
          </div>
          <div className="p-3 bg-white rounded-lg border border-slate-200 shadow-xs">
            <span className="text-[11px] font-mono text-slate-600">02. RESOLUTION</span>
            <h4 className="text-sm font-semibold text-slate-900 mt-1">Entity Match</h4>
            <p className="text-xs text-slate-500 mt-0.5">Map synonyms, recognize typos, and isolate ambiguous mixtures.</p>
          </div>
          <div className="p-3 bg-white rounded-lg border border-slate-200 shadow-xs">
            <span className="text-[11px] font-mono text-slate-600">03. CHEMISTRY</span>
            <h4 className="text-sm font-semibold text-slate-900 mt-1">Molecular Truth</h4>
            <p className="text-xs text-slate-500 mt-0.5">Explicit formulas, CAS, and weights when verifiable.</p>
          </div>
          <div className="p-3 bg-white rounded-lg border border-slate-200 shadow-xs">
            <span className="text-[11px] font-mono text-slate-600">04. CONTEXT</span>
            <h4 className="text-sm font-semibold text-slate-900 mt-1">Evidence Base</h4>
            <p className="text-xs text-slate-500 mt-0.5">Authoritative citations explaining technological function.</p>
          </div>
        </div>
      </section>

      {/* Product Principles & Scientific Integrity */}
      <section className="max-w-5xl mx-auto px-4">
        <div className="bg-slate-900 text-slate-100 rounded-2xl p-6 sm:p-8">
          <div className="max-w-2xl">
            <span className="text-xs font-mono tracking-wider text-slate-300 uppercase">
              Scientific Principles
            </span>
            <h2 className="text-xl sm:text-2xl font-bold mt-1 text-white">
              Why LabelLens rejects "Clean" vs "Toxic" binary tropes.
            </h2>
            <p className="mt-2 text-sm text-slate-300 leading-relaxed">
              Standard consumer apps assign superficial green/red health grades that ignore chemical reality.
              In physical chemistry, toxicity is dictated by dose, molecular matrix, and physiological exposure route.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-6 pt-6 border-t border-slate-800 text-xs text-slate-300">
            <div className="space-y-1.5">
              <span className="font-semibold text-white block text-sm">Truth Before Fluency</span>
              <p>Unknown is always better than invented. If an ingredient is an umbrella term like "Natural flavouring", we acknowledge the uncertainty rather than fabricating a molecule.</p>
            </div>
            <div className="space-y-1.5">
              <span className="font-semibold text-white block text-sm">No Pseudo-Scoring</span>
              <p>We do not score products out of 100 or designate chemicals as good or evil. We explain exactly what each component does and why it was formulated.</p>
            </div>
            <div className="space-y-1.5">
              <span className="font-semibold text-white block text-sm">Authoritative Grounding</span>
              <p>Every functional statement maps to published regulatory monographs (EFSA, US FDA 21 CFR, Codex Alimentarius, CIR) or peer-reviewed literature.</p>
            </div>
          </div>
        </div>
      </section>

      {/* Demo Products Grid */}
      <section className="max-w-5xl mx-auto px-4">
        <div className="flex flex-col sm:flex-row sm:items-end justify-between mb-6 gap-2">
          <div>
            <span className="text-xs font-mono uppercase tracking-wider text-slate-600">Curated Lab Demonstrations</span>
            <h3 className="text-xl font-bold text-slate-900">Explore Demo Formulations</h3>
          </div>
          <p className="text-xs text-slate-500 max-w-sm">
            Select a verified formulation to inspect its chemical topology, functional roles, and evidence base.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {DEMO_PRODUCTS.map((prod) => {
            const hasTypoScenario = prod.id === 'prod_cocoa_spread';
            return (
              <div
                key={prod.id}
                className="bg-white border border-slate-200 rounded-xl p-5 hover:border-slate-400 hover:shadow-sm transition-all flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center justify-between text-xs text-slate-600 mb-2">
                    <span className="font-medium text-slate-700">{prod.brand}</span>
                    <span className="font-mono text-[11px] px-2 py-0.5 bg-slate-100 rounded text-slate-700">
                      {prod.domain}
                    </span>
                  </div>

                  <h4 className="text-base font-semibold text-slate-900">{prod.name}</h4>

                  <p className="text-xs text-slate-600 mt-2 font-mono bg-slate-50 p-2.5 rounded-lg border border-slate-100 leading-relaxed">
                    {prod.labelText}
                  </p>

                  {hasTypoScenario && (
                    <div className="mt-3 text-xs text-amber-700 bg-amber-50/70 border border-amber-200/80 p-2 rounded-lg flex items-center gap-1.5">
                      <span className="font-mono font-bold">OCR Demo:</span>
                      <span>Contains intentional typo ("Emulsifer") ready for user correction in scanner.</span>
                    </div>
                  )}

                  {prod.id === 'prod_peanut_butter_bar' && (
                    <div className="mt-3 text-xs text-blue-700 bg-blue-50/70 border border-blue-200/80 p-2 rounded-lg flex items-center gap-1.5">
                      <span className="font-mono font-bold">Nested Syntax:</span>
                      <span>3 primary components · 7 declared sub-ingredients with percentages & INS codes.</span>
                    </div>
                  )}

                  <div className="mt-3 flex items-center gap-3 text-xs text-slate-500">
                    <span>
                      {prod.ingredientsTree && prod.ingredientsTree.length > 0
                        ? `${prod.ingredientsTree.length} primary (${prod.ingredients.length} total)`
                        : `${prod.ingredients.length} components`}
                    </span>
                    <span>·</span>
                    <span>{prod.ingredients.filter(i => i.matchStatus === 'Matched').length} Defined Entities</span>
                    <span>·</span>
                    <span>{prod.ingredients.filter(i => i.matchStatus === 'Unknown').length > 0 ? 'Unresolved Fractions' : 'All Mapped'}</span>
                  </div>
                </div>

                <div className="mt-5 pt-3 border-t border-slate-100 flex items-center justify-between gap-2">
                  <button
                    onClick={() => onSelectProduct(prod)}
                    className="text-xs font-semibold text-slate-900 hover:text-blue-600 flex items-center gap-1 cursor-pointer py-1"
                  >
                    <span>Inspect Analysis</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>

                  <button
                    onClick={() => onStartScan(prod)}
                    className="text-xs font-medium text-slate-600 hover:text-slate-900 px-2.5 py-1 bg-slate-100 hover:bg-slate-200 rounded-md transition-colors cursor-pointer"
                  >
                    Test Scan Flow
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* Educational Quick Link */}
      <section className="max-w-5xl mx-auto px-4">
        <div className="bg-slate-100/70 border border-slate-200/80 rounded-xl p-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <BookOpen className="w-5 h-5 text-slate-700 shrink-0 mt-0.5" />
            <div>
              <h4 className="text-sm font-semibold text-slate-900">Curious how normalization & entity matching work?</h4>
              <p className="text-xs text-slate-600 mt-0.5">
                Learn why optical character recognition generates errors on curved containers and why complex mixtures cannot be represented as simple SMILES strings.
              </p>
            </div>
          </div>
          <button
            onClick={() => onNavigate('learn')}
            className="text-xs font-semibold text-slate-900 hover:text-blue-600 whitespace-nowrap flex items-center gap-1 cursor-pointer shrink-0"
          >
            <span>Read Educational Guide</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </section>
    </div>
  );
};
