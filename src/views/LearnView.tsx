import React from 'react';
import { BookOpen, AlertOctagon, HelpCircle, Layers, CheckCircle2, Shield, Info } from 'lucide-react';

export const LearnView: React.FC = () => {
  return (
    <div className="max-w-4xl mx-auto px-4 py-6 space-y-10">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2 text-xs font-mono text-slate-500 mb-1">
          <span>EDUCATIONAL FOUNDATIONS</span>
          <span>·</span>
          <span>COMPUTATIONAL LABEL SCIENCE</span>
        </div>
        <h1 className="text-2xl sm:text-3xl font-bold text-slate-900">
          Core Methodologies & Principles
        </h1>
        <p className="text-sm text-slate-600 mt-1 max-w-2xl leading-relaxed">
          How LabelLens navigates optical extraction, chemical entity matching, and scientific evidence without resorting to marketing dogma or fear-based grading.
        </p>
      </div>

      {/* Module 1: Why LabelLens rejects GOOD / BAD labels */}
      <section className="bg-slate-900 text-white rounded-2xl p-6 sm:p-8 space-y-4">
        <div className="flex items-center gap-2 text-rose-400 font-mono text-xs uppercase tracking-wider">
          <AlertOctagon className="w-4 h-4" />
          <span>Core Principle 01</span>
        </div>
        <h2 className="text-xl sm:text-2xl font-bold">
          Why LabelLens Refuses Binary "Good vs Bad" Chemical Ratings
        </h2>
        <div className="text-sm text-slate-300 space-y-3 leading-relaxed">
          <p>
            Popular consumer scanning apps employ simplified traffic-light scorecards (green=safe, red=toxic).
            From a toxicological standpoint, this is fundamentally unscientific.
          </p>
          <div className="p-4 bg-slate-800/80 rounded-xl border border-slate-700 font-mono text-xs text-slate-200">
            "Sola dosis facit venenum" (The dose alone makes the poison) — Paracelsus, 1538.
          </div>
          <p>
            Water (<span className="font-mono text-slate-200">H₂O</span>) induces fatal hyponatremia at acute high volumes;
            botulinum toxin is lethal at nanogram doses yet therapeutically safe for localized spasms at picogram levels.
            Chemical safety cannot be disassociated from <strong>dosage, formulation matrix, physiological route of exposure, and frequency</strong>.
          </p>
          <p>
            LabelLens reports verified chemical facts, functional technological roles, and peer-reviewed regulatory monographs.
            We leave value judgments to qualified toxicologists and informed consumers.
          </p>
        </div>
      </section>

      {/* Module 2: The Label Intelligence Pipeline */}
      <section className="space-y-6">
        <div>
          <span className="text-xs font-mono text-slate-600 uppercase tracking-wider">Technical Architecture</span>
          <h2 className="text-xl font-bold text-slate-900 mt-0.5">
            The LabelLens Computational Pipeline
          </h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Step 1: OCR */}
          <div className="bg-white p-5 rounded-xl border border-slate-200 space-y-2">
            <span className="text-[11px] font-mono px-2 py-0.5 bg-slate-100 rounded text-slate-700 font-semibold">
              01. Optical Extraction (OCR)
            </span>
            <h3 className="text-sm font-bold text-slate-900">What OCR Does & Why It Errors</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Optical Character Recognition converts pixels from curved cylindrical cans, folds, or glare into raw Unicode text.
              Because packaging surfaces bend and print contrasts vary, OCR frequently introduces typos (such as <strong className="text-slate-800">"Emulsifer"</strong> instead of "Emulsifier").
              LabelLens keeps the OCR step editable so human domain oversight verifies accuracy before computation.
            </p>
          </div>

          {/* Step 2: Normalization */}
          <div className="bg-white p-5 rounded-xl border border-slate-200 space-y-2">
            <span className="text-[11px] font-mono px-2 py-0.5 bg-slate-100 rounded text-slate-700 font-semibold">
              02. String Normalization
            </span>
            <h3 className="text-sm font-bold text-slate-900">Standardizing Label Syntax</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Packaged goods use varied naming standards: "Sugar", "Cane sugar", "Refined sucrose", or "E 330" vs "Citric acid".
              Normalization standardizes case, removes branding noise, and resolves commercial aliases to an authoritative canonical index.
            </p>
          </div>

          {/* Step 3: Entity Matching */}
          <div className="bg-white p-5 rounded-xl border border-slate-200 space-y-2">
            <span className="text-[11px] font-mono px-2 py-0.5 bg-slate-100 rounded text-slate-700 font-semibold">
              03. Entity Matching vs Hallucination
            </span>
            <h3 className="text-sm font-bold text-slate-900">Truth Before Fluency</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              When software matches an ingredient string to a chemical registry, confidence scoring is crucial.
              If an entity is unknown or ambiguous, LabelLens explicitly flags it as <strong className="text-slate-800">"Unknown / Unresolved"</strong>.
              We never fabricate a plausible CAS number or SMILES string when genuine empirical identification is lacking.
            </p>
          </div>

          {/* Step 4: Complex Mixtures */}
          <div className="bg-white p-5 rounded-xl border border-slate-200 space-y-2">
            <span className="text-[11px] font-mono px-2 py-0.5 bg-slate-100 rounded text-slate-700 font-semibold">
              04. Representation Limitations
            </span>
            <h3 className="text-sm font-bold text-slate-900">Why Not Every Ingredient Has One Molecule</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Ingredients like <strong className="text-slate-800">"Natural flavouring"</strong>, <strong className="text-slate-800">"Soy lecithin"</strong>, or <strong className="text-slate-800">"Whey powder"</strong> are multi-component biological mixtures or extracts.
              Assigning a single 2D skeletal formula or exact molecular weight to a mixture is physically invalid. LabelLens categorizes representation types strictly.
            </p>
          </div>
        </div>
      </section>

      {/* Module 3: Molecular Descriptors Decoded */}
      <section className="bg-white rounded-2xl border border-slate-200 p-6 space-y-4">
        <div>
          <span className="text-xs font-mono text-slate-600 uppercase tracking-wider">Chemical Nomenclature</span>
          <h2 className="text-lg font-bold text-slate-900 mt-0.5">
            Understanding Molecular Facts
          </h2>
        </div>

        <div className="divide-y divide-slate-100 text-xs">
          <div className="py-3 flex flex-col sm:flex-row sm:items-start justify-between gap-2">
            <span className="font-mono font-bold text-slate-900 w-36 shrink-0">Chemical Formula</span>
            <p className="text-slate-600 flex-1">
              The stoichiometric count of each atom in a discrete compound (e.g. <span className="font-mono text-slate-800">C12H22O11</span> for Sucrose). Only applicable to defined stoichiometric chemical entities, not agricultural mixtures.
            </p>
          </div>

          <div className="py-3 flex flex-col sm:flex-row sm:items-start justify-between gap-2">
            <span className="font-mono font-bold text-slate-900 w-36 shrink-0">Molecular Weight (g/mol)</span>
            <p className="text-slate-600 flex-1">
              The sum of standard atomic weights of constituent atoms. For polymers (like xanthan gum) or polydisperse lipids (like lecithin), molecular weights are distributed ranges rather than single integers.
            </p>
          </div>

          <div className="py-3 flex flex-col sm:flex-row sm:items-start justify-between gap-2">
            <span className="font-mono font-bold text-slate-900 w-36 shrink-0">CAS Registry Number</span>
            <p className="text-slate-600 flex-1">
              A unique numerical identifier assigned by the Chemical Abstracts Service (CAS) of the American Chemical Society, providing universal disambiguation across international languages.
            </p>
          </div>

          <div className="py-3 flex flex-col sm:flex-row sm:items-start justify-between gap-2">
            <span className="font-mono font-bold text-slate-900 w-36 shrink-0">SMILES Notation</span>
            <p className="text-slate-600 flex-1">
              Simplified Molecular Input Line Entry System. An ASCII string encoding 2D chemical connectivity (e.g. bonds, rings, branching) that computational algorithms can process.
            </p>
          </div>
        </div>
      </section>

      {/* Module 4: Why Evidence & Confidence Matter */}
      <section className="bg-slate-50 rounded-2xl border border-slate-200 p-6 space-y-3">
        <div className="flex items-center gap-2">
          <Shield className="w-4 h-4 text-blue-600" />
          <h3 className="text-sm font-bold text-slate-900">
            Why Evidence & Source Transparency Matter
          </h3>
        </div>
        <p className="text-xs text-slate-600 leading-relaxed">
          LabelLens anchors its functional claims exclusively to published scientific literature and statutory safety panels:
        </p>
        <ul className="text-xs text-slate-600 space-y-1.5 pl-4 list-disc">
          <li><strong>EFSA (European Food Safety Authority):</strong> Rigorous peer-reviewed risk assessment monographs for food additives and dietary sweeteners.</li>
          <li><strong>US FDA (21 CFR):</strong> Codified regulations and GRAS (Generally Recognized as Safe) determinations.</li>
          <li><strong>CIR (Cosmetic Ingredient Review):</strong> Independent toxicological panels evaluating dermal cosmetic ingredients.</li>
          <li><strong>Codex Alimentarius (FAO/WHO):</strong> International food standards harmonizing ingredient purity specifications worldwide.</li>
        </ul>
      </section>
    </div>
  );
};
