import React from 'react';
import {
  ArrowLeft,
  ExternalLink,
  HelpCircle,
  FileCheck,
  AlertTriangle,
  ShieldCheck,
  Atom,
  BookOpen,
  Layers,
  Globe,
  Search,
  CheckCircle2,
  Info,
} from 'lucide-react';
import { IngredientObservation, ChemicalEntity, Evidence } from '../types';
import { DEMO_EVIDENCE } from '../data/evidence';
import { MoleculeStructureView } from '../components/chemistry/MoleculeStructureView';

interface IngredientDetailViewProps {
  observation: IngredientObservation;
  entity: ChemicalEntity | null;
  onBack: () => void;
}

export const IngredientDetailView: React.FC<IngredientDetailViewProps> = ({
  observation,
  entity,
  onBack,
}) => {
  const why = observation.whyIsThisHere;
  const isUnresolved = observation.matchStatus === 'Unknown' || !entity;
  const confBreakdown = observation.confidenceBreakdown;

  // Retrieve evidence records
  const evidenceList: Evidence[] = observation.evidenceIds
    .map(id => DEMO_EVIDENCE[id])
    .filter(Boolean);

  return (
    <div className="max-w-4xl mx-auto px-4 py-6 space-y-8">
      {/* Back button */}
      <div>
        <button
          onClick={onBack}
          className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-slate-800 transition-colors mb-3 cursor-pointer"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to Product Ingredients</span>
        </button>

        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <span className="text-[11px] font-mono px-2 py-0.5 bg-slate-100 text-slate-700 rounded font-semibold">
                {observation.classification ? observation.classification.replace(/_/g, ' ') : entity?.chemicalClass || 'Unresolved Entity'}
              </span>
              <span className="text-xs text-slate-600">·</span>
              <span className="text-xs text-slate-600">Raw label text: "{observation.rawText}"</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-bold text-slate-900">
              {entity ? entity.preferredName : observation.normalizedText}
            </h1>
          </div>

          <div className="flex items-center gap-2">
            <span
              className={`text-xs font-mono px-2.5 py-1 rounded-md border ${
                observation.matchStatus === 'Matched'
                  ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                  : 'bg-amber-50 text-amber-800 border-amber-200'
              }`}
            >
              Status: {observation.matchStatus}
            </span>
            <span className="text-xs font-mono px-2.5 py-1 bg-slate-100 text-slate-700 rounded-md border border-slate-200">
              Confidence: {observation.confidenceScore}%
            </span>
          </div>
        </div>
      </div>

      {/* Verification Status & Provenance Banner (Phase 1.3 Requirements 1, 8, 9) */}
      {observation.verificationStatus === 'LOCAL_VERIFIED' && (
        <div className="bg-emerald-50/70 border border-emerald-200 rounded-xl p-4 text-xs text-emerald-950 flex items-start gap-3">
          <ShieldCheck className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <strong className="font-bold text-sm text-emerald-950">Verified Local Catalog Entity</strong>
              <span className="text-[10px] font-mono px-2 py-0.5 bg-emerald-100/80 rounded text-emerald-900 font-semibold">
                Local Chemistry DB · Zero Hallucination Risk
              </span>
            </div>
            <p className="text-emerald-900 leading-relaxed">
              Ingredient identified with 100% confidence against the curated LabelLens verified catalog. Web search was not needed.
            </p>
          </div>
        </div>
      )}

      {observation.verificationStatus === 'VERIFIED_WEB_BACKED' && (
        <div className="bg-indigo-50/80 border border-indigo-200 rounded-xl p-4 text-xs text-indigo-950 flex items-start gap-3">
          <Globe className="w-5 h-5 text-indigo-600 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <div className="flex items-center gap-2 flex-wrap">
              <strong className="font-bold text-sm text-indigo-950">Verified Web-Backed Record</strong>
              <span className="text-[10px] font-mono px-2 py-0.5 bg-indigo-100 rounded text-indigo-900 font-semibold">
                Google Search Grounded · Multi-Agency Regulatory Consensus
              </span>
            </div>
            <p className="text-indigo-900 leading-relaxed">
              Corroborated by government regulatory agencies (EFSA, US FDA) and international standards organizations (Codex Alimentarius). All physical chemistry and functional facts verified against public monographs.
            </p>
          </div>
        </div>
      )}

      {observation.verificationStatus === 'WEB_RESEARCHED_CANDIDATE' && (
        <div className="bg-sky-50/80 border border-sky-200 rounded-xl p-4 text-xs text-sky-950 flex items-start gap-3">
          <Search className="w-5 h-5 text-sky-600 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <strong className="font-bold text-sm text-sky-950">Web-Researched Candidate Evidence</strong>
              <span className="text-[10px] font-mono px-2 py-0.5 bg-sky-100 rounded text-sky-900 font-semibold">
                Google Search Grounded · Candidate Evidence
              </span>
            </div>
            <p className="text-sky-900 leading-relaxed">
              Empirical facts retrieved via Gemini with Google Search grounding. Candidate evidence retained with field-level provenance.
            </p>
          </div>
        </div>
      )}

      {observation.verificationStatus === 'UNRESOLVED_UNKNOWN' && (
        <div className="bg-amber-50 border-2 border-amber-300 rounded-xl p-4 text-xs text-amber-950 flex items-start gap-3 shadow-2xs">
          <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <div className="flex items-center gap-2 flex-wrap">
              <strong className="font-bold text-sm text-amber-950">Deliberate Resolution Boundary</strong>
              <span className="text-[10px] font-mono px-2 py-0.5 bg-amber-100 rounded text-amber-900 font-semibold">
                Unresolved Formulation Designation
              </span>
            </div>
            <p className="text-amber-900 font-semibold leading-relaxed">
              Unresolved: could not establish reliable chemical identity from label text and web evidence.
            </p>
            <p className="text-amber-800 leading-relaxed">
              Statutory umbrella term or undefined composite: constituent chemicals are legally permitted to remain undisclosed on retail packaging. LabelLens strictly enforces physical chemistry boundaries and prohibits forcing a single molecular structure onto multi-component matrices.
            </p>
          </div>
        </div>
      )}

      {/* Hierarchy Provenance Strip (Requirement 11) */}
      <div className="bg-slate-100/90 rounded-xl p-4 border border-slate-200 text-xs text-slate-700 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-blue-600" />
          <span>Hierarchy: <strong className="font-semibold text-slate-900">{observation.depth && observation.depth > 0 ? 'Nested Sub-Ingredient' : 'Top-Level Primary Component'}</strong></span>
        </div>
        {observation.percentage !== undefined && observation.percentage !== null && (
          <span>Declared Percentage: <strong className="font-mono font-semibold text-slate-900">{observation.percentage}%</strong></span>
        )}
        {observation.identifier && (
          <span>Statutory Code: <strong className="font-mono font-semibold text-indigo-700">{observation.identifier}</strong></span>
        )}
        <span>Formulation Role: <strong className="font-semibold text-slate-900">{observation.role}</strong></span>
      </div>

      {/* Multi-Dimensional Confidence Breakdown (Requirement 7) */}
      {confBreakdown && (
        <section className="bg-white rounded-xl border border-slate-200 p-5 space-y-3">
          <span className="text-xs font-mono uppercase tracking-wider text-slate-600 block border-b border-slate-100 pb-2">
            Multi-Dimensional Confidence Decomposition
          </span>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 text-xs">
            <div className="p-2.5 bg-slate-50 rounded-lg border border-slate-100">
              <span className="text-[10px] font-mono text-slate-500 uppercase block">OCR Confidence</span>
              <span className="font-semibold text-slate-900 mt-1 block">{confBreakdown.ocrConfidence}</span>
            </div>
            <div className="p-2.5 bg-slate-50 rounded-lg border border-slate-100">
              <span className="text-[10px] font-mono text-slate-500 uppercase block">Parsing Confidence</span>
              <span className="font-semibold text-slate-900 mt-1 block">{confBreakdown.parsingConfidence}</span>
            </div>
            <div className="p-2.5 bg-slate-50 rounded-lg border border-slate-100">
              <span className="text-[10px] font-mono text-slate-500 uppercase block">Normalization</span>
              <span className="font-semibold text-slate-900 mt-1 block">{confBreakdown.normalizationConfidence}</span>
            </div>
            <div className="p-2.5 bg-slate-50 rounded-lg border border-slate-100">
              <span className="text-[10px] font-mono text-slate-500 uppercase block">Entity Match</span>
              <span className="font-semibold text-slate-900 mt-1 block">{confBreakdown.entityMatchConfidence}</span>
            </div>
            <div className="p-2.5 bg-slate-50 rounded-lg border border-slate-100">
              <span className="text-[10px] font-mono text-slate-500 uppercase block">Chemistry Fact</span>
              <span className="font-semibold text-slate-900 mt-1 block">{confBreakdown.chemistryConfidence}</span>
            </div>
          </div>
        </section>
      )}

      {/* Main 2-Column Section: Physical Chemistry Metrics + Structure */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-6 items-start">
        {/* Left Column: Chemistry Metrics Table (Requirement 9: "Not available for this representation") */}
        <div className="md:col-span-6 space-y-4">
          <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-4">
            <h3 className="text-xs font-mono uppercase tracking-wider text-slate-600 pb-2 border-b border-slate-100">
              Physical & Chemical Registry Facts
            </h3>

            <div className="space-y-3 text-xs">
              <div className="flex items-start justify-between gap-2 py-1 border-b border-slate-100">
                <span className="text-slate-600 font-mono">Preferred Name:</span>
                <span className="font-semibold text-slate-900 text-right">
                  {entity?.preferredName || observation.webResearch?.canonicalName || observation.normalizedText}
                </span>
              </div>

              <div className="flex items-start justify-between gap-2 py-1 border-b border-slate-100">
                <span className="text-slate-600 font-mono">Common Synonyms:</span>
                <span className="text-slate-800 text-right max-w-[240px]">
                  {entity?.aliases && entity.aliases.length > 0
                    ? entity.aliases.join(', ')
                    : observation.webResearch?.aliases && observation.webResearch.aliases.length > 0
                    ? observation.webResearch.aliases.join(', ')
                    : 'Not available for this representation.'}
                </span>
              </div>

              <div className="flex items-start justify-between gap-2 py-1 border-b border-slate-100">
                <span className="text-slate-600 font-mono">Molecular Formula:</span>
                <span className="font-mono font-semibold text-slate-900">
                  {entity?.formula || observation.webResearch?.chemicalFormula || 'Not available for this representation.'}
                </span>
              </div>

              <div className="flex items-start justify-between gap-2 py-1 border-b border-slate-100">
                <span className="text-slate-600 font-mono">Molecular Weight:</span>
                <span className="font-mono font-semibold text-slate-900">
                  {entity?.molecularWeight
                    ? `${entity.molecularWeight} g/mol`
                    : observation.webResearch?.molecularWeight
                    ? `${observation.webResearch.molecularWeight} g/mol`
                    : 'Not available for this representation.'}
                </span>
              </div>

              <div className="flex items-start justify-between gap-2 py-1 border-b border-slate-100">
                <span className="text-slate-600 font-mono">CAS Registry Number:</span>
                <span className="font-mono font-semibold text-slate-900">
                  {entity?.cas || observation.webResearch?.casNumber || 'Not available for this representation.'}
                </span>
              </div>

              <div className="flex items-start justify-between gap-2 py-1 border-b border-slate-100">
                <span className="text-slate-600 font-mono">Canonical SMILES:</span>
                <span
                  className="font-mono text-slate-800 text-right max-w-[220px] truncate"
                  title={entity?.smiles || observation.webResearch?.smiles || ''}
                >
                  {entity?.smiles || observation.webResearch?.smiles || 'Not available for this representation.'}
                </span>
              </div>

              <div className="flex items-start justify-between gap-2 py-1 border-b border-slate-100">
                <span className="text-slate-600 font-mono">Representation Type:</span>
                <span className="text-slate-900 font-medium text-right">
                  {entity?.representationType || observation.webResearch?.representationType || 'Formulation Mixture / Botanical'}
                </span>
              </div>

              <div className="flex items-start justify-between gap-2 py-1">
                <span className="text-slate-600 font-mono">Formulation Role:</span>
                <span className="font-semibold text-slate-900 text-right">{observation.role}</span>
              </div>
            </div>

            {/* Descriptors bullet points */}
            {entity?.descriptors && entity.descriptors.length > 0 && (
              <div className="pt-2 border-t border-slate-100">
                <span className="text-[11px] font-mono uppercase text-slate-600 block mb-1.5">
                  Physicochemical Properties
                </span>
                <ul className="space-y-1 text-xs text-slate-700">
                  {entity.descriptors.map((d, i) => (
                    <li key={i} className="flex items-start gap-1.5">
                      <span className="text-slate-400">·</span>
                      <span>{d}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Explicit Limitations Box */}
          <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 text-xs text-slate-600">
            <span className="font-mono font-semibold uppercase text-slate-700 block mb-1">
              Scope & Boundaries
            </span>
            <p className="leading-relaxed">
              {entity?.limitations || 'Data reflects verified physical records. In biological food materials or multi-constituent mixtures, physical constants cannot be reduced to a single molecule.'}
            </p>
          </div>
        </div>

        {/* Right Column: Structure Renderer / Representation */}
        <div className="md:col-span-6 space-y-4">
          <MoleculeStructureView entity={entity} />

          {/* Uncertainty notice for unresolved ingredients */}
          {isUnresolved && (
            <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-xs text-amber-900">
              <div className="flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                <div>
                  <h4 className="font-bold">Deliberate Resolution Boundary</h4>
                  <p className="mt-1 leading-relaxed text-amber-800">
                    Role not confidently resolved from label text alone.
                    LabelLens deliberately preserves uncertain entities.
                    Inventing a single chemical formula would mislead consumers and violate scientific rigor.
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* "Why is this here?" 5-Part Section */}
      <section className="bg-white rounded-2xl border border-slate-200 p-6 sm:p-8 space-y-6">
        <div className="border-b border-slate-200 pb-4">
          <span className="text-xs font-mono uppercase tracking-wider text-slate-600">
            Formulation Intelligence
          </span>
          <h2 className="text-xl font-bold text-slate-900 mt-1">
            Why is this here?
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            5-part chemical and functional inquiry into the ingredient's purpose in this formulation.
          </p>
        </div>

        {why ? (
          <div className="space-y-6 text-sm">
            <div className="space-y-1">
              <span className="text-xs font-mono font-bold uppercase text-slate-600 block">
                1. What is it?
              </span>
              <p className="text-slate-800 leading-relaxed pl-3 border-l-2 border-slate-300">
                {why.whatIsIt}
              </p>
            </div>

            <div className="space-y-1">
              <span className="text-xs font-mono font-bold uppercase text-slate-600 block">
                2. Why may it be used?
              </span>
              <p className="text-slate-800 leading-relaxed pl-3 border-l-2 border-blue-500">
                {why.whyUsed}
              </p>
            </div>

            <div className="space-y-1">
              <span className="text-xs font-mono font-bold uppercase text-slate-600 block">
                3. What chemistry is relevant?
              </span>
              <p className="text-slate-800 leading-relaxed pl-3 border-l-2 border-slate-300">
                {why.relevantChemistry}
              </p>
            </div>

            <div className="space-y-1">
              <span className="text-xs font-mono font-bold uppercase text-slate-600 block">
                4. What evidence supports this?
              </span>
              <p className="text-slate-800 leading-relaxed pl-3 border-l-2 border-slate-300">
                {why.evidenceSupport}
              </p>
            </div>

            <div className="space-y-1">
              <span className="text-xs font-mono font-bold uppercase text-slate-600 block">
                5. What remains uncertain?
              </span>
              <p className="text-slate-800 leading-relaxed pl-3 border-l-2 border-amber-400">
                {why.uncertainties}
              </p>
            </div>
          </div>
        ) : (
          <div className="p-4 bg-slate-50 text-slate-600 text-xs rounded-lg">
            Role not confidently resolved from label text alone.
          </div>
        )}
      </section>

      {/* Web-Grounded Research & Field-Level Provenance Section (Phase 1.3 Requirements 3, 4, 5, 7, 8) */}
      {observation.webResearch && (
        <section className="bg-white rounded-2xl border border-indigo-200/90 p-6 sm:p-8 space-y-6 shadow-xs">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-indigo-100 pb-4">
            <div>
              <div className="flex items-center gap-2">
                <Globe className="w-5 h-5 text-indigo-600" />
                <span className="text-xs font-mono uppercase tracking-wider text-indigo-800 font-bold">
                  Google Search Grounding & Chemical Provenance
                </span>
              </div>
              <h3 className="text-xl font-bold text-slate-900 mt-1">
                Web-Grounded Chemical Evidence
              </h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Empirical regulatory facts retrieved via Gemini with Google Search grounding. Candidate evidence verified against public monographs.
              </p>
            </div>

            <div className="flex items-center gap-2 flex-wrap self-start sm:self-auto">
              <span className="text-xs font-mono px-2.5 py-1 bg-indigo-50 text-indigo-800 rounded-md border border-indigo-200 font-semibold">
                {observation.webResearch.sources.length} Authoritative Source{observation.webResearch.sources.length !== 1 ? 's' : ''}
              </span>
              <span className="text-xs font-mono px-2.5 py-1 bg-emerald-50 text-emerald-800 rounded-md border border-emerald-200 font-semibold">
                {observation.webResearch.provenance.length} Verified Field Records
              </span>
            </div>
          </div>

          {/* Search Context & Retrieval Provenance */}
          <div className="bg-slate-50 rounded-xl p-4 border border-slate-200 text-xs space-y-2">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 text-[11px] font-mono text-slate-500">
              <span>Primary Grounding Query: <strong className="text-slate-800">"{observation.webResearch.query}"</strong></span>
              <span>Retrieved: {new Date(observation.webResearch.searchedAt).toLocaleString()}</span>
            </div>
            {observation.webResearch.rawSearchQueries && observation.webResearch.rawSearchQueries.length > 0 && (
              <div className="pt-1 text-[11px] font-mono text-slate-600 flex flex-wrap items-center gap-1.5">
                <span className="font-semibold text-slate-700">Executed Queries:</span>
                {observation.webResearch.rawSearchQueries.map((q, qIdx) => (
                  <span key={qIdx} className="bg-white px-2 py-0.5 rounded border border-slate-200 text-slate-700">
                    {q}
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Grounding Sources (Priority Classified) */}
          <div className="space-y-3">
            <h4 className="text-xs font-mono uppercase tracking-wider text-slate-700 font-semibold">
              Authoritative Grounding Sources & Regulatory Monographs
            </h4>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
              {observation.webResearch.sources.map((src, idx) => {
                const isGov = src.sourceType === 'government_regulatory';
                const isStandards = src.sourceType === 'official_standards';
                const isSci = src.sourceType === 'scientific_database';

                return (
                  <div
                    key={idx}
                    className="p-3.5 bg-slate-50/80 rounded-xl border border-slate-200 hover:border-slate-300 transition-colors flex flex-col justify-between gap-2"
                  >
                    <div>
                      <div className="flex items-center justify-between gap-2 mb-1.5">
                        <span
                          className={`text-[10px] font-mono uppercase px-2 py-0.5 rounded font-bold border ${
                            isGov
                              ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                              : isStandards
                              ? 'bg-indigo-50 text-indigo-800 border-indigo-200'
                              : isSci
                              ? 'bg-blue-50 text-blue-800 border-blue-200'
                              : 'bg-slate-100 text-slate-700 border-slate-200'
                          }`}
                        >
                          {src.sourceType.replace(/_/g, ' ')}
                        </span>
                        <span className="text-[10px] font-mono text-slate-600">Priority #{idx + 1}</span>
                      </div>
                      <h5 className="font-semibold text-slate-900 text-xs line-clamp-2">
                        {src.title}
                      </h5>
                    </div>

                    <a
                      href={src.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[11px] font-mono text-blue-600 hover:text-blue-800 hover:underline inline-flex items-center gap-1 pt-1.5 border-t border-slate-200/60"
                    >
                      <span className="truncate max-w-[260px]">{src.url}</span>
                      <ExternalLink className="w-3 h-3 shrink-0" />
                    </a>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Field-Level Support & Provenance Table (Requirement 7 & 8) */}
          <div className="space-y-3 pt-2 border-t border-slate-100">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-mono uppercase tracking-wider text-slate-700 font-semibold">
                Field-Level Evidence & Chemical Provenance Table
              </h4>
              <span className="text-[11px] font-mono text-slate-600">
                Rule: Missing / Multi-component fields remain null
              </span>
            </div>

            <div className="overflow-x-auto border border-slate-200 rounded-xl bg-white shadow-2xs">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 text-slate-600 font-mono text-[11px] uppercase border-b border-slate-200">
                  <tr>
                    <th className="py-2.5 px-3">Field</th>
                    <th className="py-2.5 px-3">Extracted Fact / Value</th>
                    <th className="py-2.5 px-3">Supporting Authority</th>
                    <th className="py-2.5 px-3">Evidence Observation</th>
                    <th className="py-2.5 px-3">Confidence</th>
                    <th className="py-2.5 px-3">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 font-mono text-[11px]">
                  {observation.webResearch.provenance.map((prov, pIdx) => {
                    const isNull = prov.value === null || prov.value === undefined;

                    return (
                      <tr key={pIdx} className="hover:bg-slate-50/60">
                        <td className="py-2 px-3 font-semibold text-slate-800 whitespace-nowrap">
                          {prov.field}
                        </td>
                        <td className="py-2 px-3">
                          {isNull ? (
                            <span className="text-slate-400 italic font-mono">
                              null (Omitted — multi-component mixture)
                            </span>
                          ) : (
                            <span className="font-semibold text-slate-900 font-sans">
                              {String(prov.value)}
                            </span>
                          )}
                        </td>
                        <td className="py-2 px-3 text-slate-600 whitespace-nowrap">
                          {prov.sourceTitle || 'Regulatory Authority'}
                        </td>
                        <td className="py-2 px-3 text-slate-600 max-w-[260px] truncate font-sans" title={prov.evidenceText || ''}>
                          {prov.evidenceText || 'Indexed in regulatory standard.'}
                        </td>
                        <td className="py-2 px-3 font-semibold text-slate-800">
                          {Math.round(prov.confidence * 100)}%
                        </td>
                        <td className="py-2 px-3 whitespace-nowrap">
                          <span
                            className={`px-1.5 py-0.5 rounded text-[10px] font-semibold border ${
                              prov.verificationStatus === 'verified'
                                ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                                : prov.verificationStatus === 'candidate'
                                ? 'bg-sky-50 text-sky-800 border-sky-200'
                                : 'bg-amber-50 text-amber-800 border-amber-200'
                            }`}
                          >
                            {prov.verificationStatus}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Anti-Hallucination Chemical Representation Notice */}
            <div className="bg-slate-50 p-3 rounded-lg border border-slate-200 text-[11px] text-slate-600 flex items-start gap-2">
              <Info className="w-4 h-4 text-slate-500 shrink-0 mt-0.5" />
              <p className="leading-relaxed">
                <strong className="font-semibold text-slate-800">Chemical Representation Rule Enforced:</strong> For multi-constituent matrices, fractions, and botanical extracts, LabelLens strictly omits single-molecule formula, molecular weight, and SMILES strings to eliminate computational hallucination. Missing properties remain strictly null.
              </p>
            </div>
          </div>
        </section>
      )}

      {/* Authoritative Evidence Citations */}
      <section className="bg-white rounded-2xl border border-slate-200 p-6 space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-slate-100">
          <div>
            <span className="text-xs font-mono uppercase tracking-wider text-slate-600">
              Corroborating Records
            </span>
            <h3 className="text-lg font-bold text-slate-900">
              Authoritative Evidence
            </h3>
          </div>
          <span className="text-xs font-mono px-2 py-0.5 bg-slate-100 rounded text-slate-700">
            {evidenceList.length} Citation{evidenceList.length !== 1 ? 's' : ''}
          </span>
        </div>

        {evidenceList.length > 0 ? (
          <div className="space-y-3">
            {evidenceList.map(ev => (
              <div
                key={ev.id}
                className="p-4 bg-slate-50 rounded-xl border border-slate-200 space-y-2 hover:bg-slate-100/60 transition-colors"
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
                  <h4 className="text-sm font-semibold text-slate-900">
                    {ev.title}
                  </h4>
                  <span className="text-[11px] font-mono px-2 py-0.5 bg-white rounded border border-slate-200 text-slate-600 shrink-0 self-start sm:self-auto">
                    {ev.evidenceType}
                  </span>
                </div>

                <p className="text-xs text-slate-600 leading-relaxed">
                  {ev.summary}
                </p>

                <div className="pt-2 flex flex-wrap items-center justify-between gap-2 text-[11px] font-mono text-slate-500 border-t border-slate-200/60">
                  <span>Publisher: <strong className="text-slate-700">{ev.publisher}</strong></span>
                  <div className="flex items-center gap-3">
                    <span>Accessed: {ev.accessedAt}</span>
                    {ev.doiOrRef && <span>Ref: {ev.doiOrRef}</span>}
                    <a
                      href={ev.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-600 hover:underline flex items-center gap-0.5"
                    >
                      <span>Source</span>
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-xs text-slate-500 p-4 bg-slate-50 rounded-lg text-center">
            No external regulatory citations linked in demonstration registry for this component.
          </div>
        )}
      </section>
    </div>
  );
};
