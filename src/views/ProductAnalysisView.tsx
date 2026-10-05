import React, { useState } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  ExternalLink,
  HelpCircle,
  CheckCircle2,
  AlertCircle,
  Scale,
  Database,
  FileText,
  Layers,
  ChevronDown,
  ChevronUp,
  Globe,
  ShieldCheck,
  Search,
  BookOpen,
} from 'lucide-react';
import { Product, IngredientObservation, ChemicalEntity, IngredientNode } from '../types';
import { DEMO_CHEMICAL_ENTITIES } from '../data/chemicalEntities';
import { DEMO_EVIDENCE } from '../data/evidence';

interface ProductAnalysisViewProps {
  product: Product;
  onSelectIngredient: (observation: IngredientObservation, entity: ChemicalEntity | null) => void;
  onBackToScan: () => void;
  onCompareWith: (product: Product) => void;
}

export const ProductAnalysisView: React.FC<ProductAnalysisViewProps> = ({
  product,
  onSelectIngredient,
  onBackToScan,
  onCompareWith,
}) => {
  const [filterRole, setFilterRole] = useState<string>('all');
  const [expandedGroupIds, setExpandedGroupIds] = useState<Record<string, boolean>>({});

  const ingredients = product.ingredients || [];
  const tree = product.ingredientsTree || [];

  // Hierarchy counting: distinguishes primary formulation ingredients from nested sub-ingredients
  const topLevelCount = tree.length > 0
    ? tree.length
    : ingredients.filter(i => !i.parentId || i.depth === 0).length || ingredients.length;

  const totalCount = ingredients.length;
  const nestedCount = Math.max(0, totalCount - topLevelCount);

  const matchedCount = ingredients.filter(i => i.matchStatus === 'Matched').length;
  const partialCount = ingredients.filter(i => i.matchStatus === 'Partially matched').length;
  const unknownCount = ingredients.filter(i => i.matchStatus === 'Unknown').length;

  // Unique functional roles
  const roles = Array.from(new Set(ingredients.map(i => i.role)));

  const filteredIngredients = filterRole === 'all'
    ? ingredients
    : ingredients.filter(i => i.role === filterRole);

  // Total unique evidence references
  const allEvidenceIds = Array.from(new Set(ingredients.flatMap(i => i.evidenceIds)));

  // Verification Status Breakdown (Phase 1.3 Requirement 8)
  const localVerifiedCount = ingredients.filter(i => i.verificationStatus === 'LOCAL_VERIFIED').length;
  const webBackedCount = ingredients.filter(i => i.verificationStatus === 'VERIFIED_WEB_BACKED').length;
  const webCandidateCount = ingredients.filter(i => i.verificationStatus === 'WEB_RESEARCHED_CANDIDATE').length;
  const unresolvedCount = ingredients.filter(i => i.verificationStatus === 'UNRESOLVED_UNKNOWN' || i.matchStatus === 'Unknown').length;

  const toggleGroup = (id: string) => {
    setExpandedGroupIds(prev => ({
      ...prev,
      [id]: !prev[id],
    }));
  };

  return (
    <div className="max-w-5xl mx-auto px-4 py-6 space-y-8">
      {/* Navigation & Header */}
      <div>
        <button
          onClick={onBackToScan}
          className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-slate-800 transition-colors mb-3 cursor-pointer"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to Label Scanner</span>
        </button>

        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs font-mono px-2 py-0.5 bg-slate-100 rounded text-slate-700 font-semibold">
                {product.domain}
              </span>
              <span className="text-xs text-slate-600">·</span>
              <span className="text-xs text-slate-600">{product.brand}</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-bold text-slate-900">
              {product.name}
            </h1>
            <p className="text-xs font-mono text-slate-600 mt-1 max-w-2xl bg-white p-2.5 rounded-lg border border-slate-200">
              {product.labelText}
            </p>
          </div>

          <button
            onClick={() => onCompareWith(product)}
            className="px-3.5 py-2 bg-white hover:bg-slate-50 border border-slate-300 text-slate-800 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all shadow-xs shrink-0 cursor-pointer"
          >
            <Scale className="w-3.5 h-3.5 text-slate-600" />
            <span>Compare Product</span>
          </button>
        </div>
      </div>

      {/* Metric Breakdown Grid (Distinguishing Top-Level vs Sub-Ingredients) */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="bg-white p-4 rounded-xl border border-slate-200">
          <span className="text-[11px] font-mono text-slate-600 uppercase block">Formulation Structure</span>
          <div className="flex items-baseline gap-1 mt-1">
            <span className="text-2xl font-bold font-mono text-slate-900">
              {topLevelCount}
            </span>
            <span className="text-xs font-mono text-slate-500">primary</span>
            {nestedCount > 0 && (
              <span className="text-xs font-mono text-blue-700 font-semibold ml-1">
                +{nestedCount} sub
              </span>
            )}
          </div>
          <span className="text-[11px] text-slate-600 mt-0.5 block">
            {totalCount} total parsed components
          </span>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200">
          <span className="text-[11px] font-mono text-slate-600 uppercase block">Matched Entities</span>
          <span className="text-2xl font-bold font-mono text-emerald-700 mt-1 block">
            {matchedCount}
          </span>
          <span className="text-[11px] text-slate-600 mt-0.5 block">Mapped to chemical registry</span>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200">
          <span className="text-[11px] font-mono text-slate-600 uppercase block">Unresolved / Ambiguous</span>
          <span className="text-2xl font-bold font-mono text-amber-700 mt-1 block">
            {unknownCount + partialCount}
          </span>
          <span className="text-[11px] text-slate-600 mt-0.5 block">Complex mixtures / umbrella</span>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200">
          <span className="text-[11px] font-mono text-slate-600 uppercase block">Evidence Monographs</span>
          <span className="text-2xl font-bold font-mono text-slate-900 mt-1 block">
            {allEvidenceIds.length}
          </span>
          <span className="text-[11px] text-slate-600 mt-0.5 block">EFSA / FDA / CIR citations</span>
        </div>
      </div>

      {/* Verification Status & Provenance Strip (Phase 1.3 Requirement 8) */}
      <div className="bg-slate-100/90 rounded-xl p-3.5 border border-slate-200 text-xs flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Database className="w-4 h-4 text-slate-700 shrink-0" />
          <span className="font-semibold text-slate-800">Entity Resolution Provenance:</span>
        </div>
        <div className="flex items-center gap-2 flex-wrap text-[11px] font-mono">
          <span className="px-2 py-0.5 bg-emerald-50 text-emerald-800 rounded border border-emerald-200 font-semibold inline-flex items-center gap-1">
            <ShieldCheck className="w-3 h-3 text-emerald-600" />
            <span>{localVerifiedCount} Local Verified</span>
          </span>
          <span className="px-2 py-0.5 bg-indigo-50 text-indigo-800 rounded border border-indigo-200 font-semibold inline-flex items-center gap-1">
            <Globe className="w-3 h-3 text-indigo-600" />
            <span>{webBackedCount} Web-Backed (Gov/Standards)</span>
          </span>
          {webCandidateCount > 0 && (
            <span className="px-2 py-0.5 bg-sky-50 text-sky-800 rounded border border-sky-200 font-semibold inline-flex items-center gap-1">
              <Search className="w-3 h-3 text-sky-600" />
              <span>{webCandidateCount} Web Candidate</span>
            </span>
          )}
          <span className="px-2 py-0.5 bg-amber-50 text-amber-800 rounded border border-amber-200 font-semibold inline-flex items-center gap-1">
            <AlertCircle className="w-3 h-3 text-amber-600" />
            <span>{unresolvedCount} Unresolved / Umbrella</span>
          </span>
        </div>
      </div>

      {/* Filter Tabs by Functional Role */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-2 border-b border-slate-200 text-xs">
        <span className="text-slate-600 font-mono text-[11px] uppercase mr-1 shrink-0">Filter Role:</span>
        <button
          onClick={() => setFilterRole('all')}
          className={`px-3 py-1 rounded-md transition-colors cursor-pointer whitespace-nowrap ${
            filterRole === 'all'
              ? 'bg-slate-900 text-white font-medium'
              : 'bg-white text-slate-600 border border-slate-200 hover:text-slate-900'
          }`}
        >
          All Components ({ingredients.length})
        </button>
        {roles.map(r => (
          <button
            key={r}
            onClick={() => setFilterRole(r)}
            className={`px-3 py-1 rounded-md transition-colors cursor-pointer whitespace-nowrap ${
              filterRole === r
                ? 'bg-slate-900 text-white font-medium'
                : 'bg-white text-slate-600 border border-slate-200 hover:text-slate-900'
            }`}
          >
            {r}
          </button>
        ))}
      </div>

      {/* Ingredients List with Formulation Group Hierarchy */}
      <div className="space-y-4">
        {filteredIngredients.map((item, index) => {
          const entity = item.chemicalEntityId ? DEMO_CHEMICAL_ENTITIES[item.chemicalEntityId] : null;
          const isUnresolvedMixture = item.matchStatus === 'Unknown' || !entity;
          const isChild = item.depth && item.depth > 0;
          const isParentGroup = item.childrenCount && item.childrenCount > 0;

          return (
            <div
              key={item.id}
              className={`rounded-xl border transition-all p-5 hover:border-slate-400 ${
                isChild
                  ? 'ml-4 sm:ml-8 bg-slate-50/70 border-slate-200'
                  : isParentGroup
                  ? 'bg-white border-slate-300 shadow-2xs'
                  : isUnresolvedMixture
                  ? 'bg-amber-50/20 border-amber-200'
                  : 'bg-white border-slate-200'
              }`}
            >
              {/* Card Header */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-slate-100">
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    {isChild && (
                      <span className="text-[11px] font-mono text-slate-400 font-semibold">
                        ↳ Sub-ingredient:
                      </span>
                    )}
                    <h3 className="text-base font-bold text-slate-900">
                      {item.normalizedText}
                    </h3>

                    {item.percentage !== undefined && item.percentage !== null && (
                      <span className="text-[11px] font-mono px-2 py-0.5 bg-blue-50 text-blue-800 rounded font-semibold border border-blue-200">
                        {item.percentage}%
                      </span>
                    )}

                    {item.identifier && (
                      <span className="text-[11px] font-mono px-2 py-0.5 bg-indigo-50 text-indigo-800 rounded font-semibold border border-indigo-200">
                        {item.identifier}
                      </span>
                    )}

                    {item.classification && (
                      <span className="text-[10px] font-mono px-1.5 py-0.5 bg-slate-100 text-slate-700 rounded border border-slate-200">
                        {item.classification.replace(/_/g, ' ')}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-slate-600 mt-1">
                    Functional Role: <strong className="font-semibold text-slate-800">{item.role}</strong>
                  </p>
                </div>

                {/* Status Badges */}
                <div className="flex items-center gap-2 shrink-0 flex-wrap sm:flex-nowrap justify-end">
                  {/* Verification Status Badge (Phase 1.3) */}
                  {item.verificationStatus === 'LOCAL_VERIFIED' && (
                    <span className="text-[11px] font-mono px-2 py-0.5 rounded border bg-emerald-50 text-emerald-800 border-emerald-200 inline-flex items-center gap-1 font-semibold">
                      <ShieldCheck className="w-3 h-3 text-emerald-600" />
                      <span>Local Verified</span>
                    </span>
                  )}
                  {item.verificationStatus === 'VERIFIED_WEB_BACKED' && (
                    <span className="text-[11px] font-mono px-2 py-0.5 rounded border bg-indigo-50 text-indigo-800 border-indigo-200 inline-flex items-center gap-1 font-semibold">
                      <Globe className="w-3 h-3 text-indigo-600" />
                      <span>Verified Web-Backed</span>
                    </span>
                  )}
                  {item.verificationStatus === 'WEB_RESEARCHED_CANDIDATE' && (
                    <span className="text-[11px] font-mono px-2 py-0.5 rounded border bg-sky-50 text-sky-800 border-sky-200 inline-flex items-center gap-1 font-semibold">
                      <Search className="w-3 h-3 text-sky-600" />
                      <span>Web Candidate</span>
                    </span>
                  )}
                  {item.verificationStatus === 'UNRESOLVED_UNKNOWN' && (
                    <span className="text-[11px] font-mono px-2 py-0.5 rounded border bg-amber-50 text-amber-800 border-amber-200 inline-flex items-center gap-1 font-semibold">
                      <AlertCircle className="w-3 h-3 text-amber-600" />
                      <span>Unresolved Umbrella</span>
                    </span>
                  )}

                  <span
                    className={`text-[11px] font-mono px-2 py-0.5 rounded border ${
                      item.matchStatus === 'Matched'
                        ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                        : item.matchStatus === 'Partially matched'
                        ? 'bg-blue-50 text-blue-800 border-blue-200'
                        : 'bg-amber-50 text-amber-800 border-amber-200'
                    }`}
                  >
                    {item.matchStatus}
                  </span>

                  <span className="text-[11px] font-mono px-2 py-0.5 bg-slate-100 text-slate-700 rounded border border-slate-200">
                    Confidence: {item.confidence} ({item.confidenceScore}%)
                  </span>
                </div>
              </div>

              {/* Chemical Availability Details */}
              <div className="mt-3 grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs text-slate-600">
                <div>
                  <span className="text-[11px] font-mono uppercase text-slate-600 block">Chemical Entity</span>
                  <span className="font-medium text-slate-900 mt-0.5 block">
                    {entity ? entity.preferredName : item.webResearch?.canonicalName || 'Not resolved to single entity'}
                  </span>
                </div>

                <div>
                  <span className="text-[11px] font-mono uppercase text-slate-600 block">Molecular Formula</span>
                  <span className="font-mono text-slate-900 mt-0.5 block">
                    {entity?.formula || item.webResearch?.chemicalFormula || 'Not applicable / Mixture'}
                  </span>
                </div>

                <div>
                  <span className="text-[11px] font-mono uppercase text-slate-600 block">Representation Type</span>
                  <span className="font-medium text-slate-900 mt-0.5 block">
                    {entity?.representationType || item.webResearch?.representationType || 'Formulation Mixture / Botanical'}
                  </span>
                </div>
              </div>

              {/* Web Grounded Research Monograph & Sources (Phase 1.3 Requirement 8) */}
              {item.webResearch && (
                <div className="mt-3 p-3.5 bg-indigo-50/50 border border-indigo-200/90 rounded-xl text-xs space-y-2.5">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
                    <div className="flex items-center gap-1.5 font-bold text-indigo-950">
                      <Globe className="w-3.5 h-3.5 text-indigo-600 shrink-0" />
                      <span>Web Grounding Consensus: {item.webResearch.canonicalName}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-mono px-2 py-0.5 bg-white text-indigo-800 rounded border border-indigo-200 font-semibold">
                        {item.webResearch.sources.length} Authoritative Source{item.webResearch.sources.length !== 1 ? 's' : ''}
                      </span>
                      <span className="text-[10px] font-mono px-2 py-0.5 bg-indigo-100 text-indigo-900 rounded font-semibold">
                        {item.webResearch.provenance.length} Verified Field Records
                      </span>
                    </div>
                  </div>

                  <p className="text-slate-700 text-xs leading-relaxed">
                    {item.webResearch.summary}
                  </p>

                  {/* Authoritative Sources Links */}
                  <div className="pt-1 flex flex-wrap items-center gap-1.5 text-[11px] font-mono">
                    <span className="text-indigo-900 font-semibold mr-1">Cited Sources:</span>
                    {item.webResearch.sources.map((src, sIdx) => (
                      <a
                        key={sIdx}
                        href={src.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-800 hover:underline bg-white px-2 py-0.5 rounded border border-slate-200 shadow-2xs"
                      >
                        <span className="max-w-[200px] truncate">{src.title}</span>
                        <ExternalLink className="w-2.5 h-2.5 shrink-0" />
                      </a>
                    ))}
                  </div>
                </div>
              )}

              {/* Separate Confidence Dimensions */}
              {item.confidenceBreakdown && (
                <div className="mt-3 p-2.5 bg-slate-50 rounded-lg border border-slate-100 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] font-mono text-slate-500">
                  <span>OCR: <strong className="text-slate-700">{item.confidenceBreakdown.ocrConfidence}</strong></span>
                  <span>·</span>
                  <span>Parsing: <strong className="text-slate-700">{item.confidenceBreakdown.parsingConfidence}</strong></span>
                  <span>·</span>
                  <span>Entity Match: <strong className="text-slate-700">{item.confidenceBreakdown.entityMatchConfidence}</strong></span>
                  <span>·</span>
                  <span>Chemistry: <strong className="text-slate-700">{item.confidenceBreakdown.chemistryConfidence}</strong></span>
                </div>
              )}

              {/* Unresolved / Ambiguous Notice (Phase 1.3 Requirement 9) */}
              {isUnresolvedMixture && (
                <div className="mt-3 p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-900 flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 text-amber-700 shrink-0 mt-0.5" />
                  <div>
                    <strong className="font-semibold">Unresolved Formulation Entity</strong>
                    <p className="mt-0.5 text-amber-800 leading-relaxed">
                      Unresolved: could not establish reliable chemical identity from label text and web evidence.
                      Statutory umbrella term or undefined composite: constituent chemicals are legally permitted to remain undisclosed on retail packaging. Physical chemistry principles strictly prohibit forcing a discrete molecular structure onto ambiguous composites or umbrella flavourings.
                    </p>
                  </div>
                </div>
              )}

              {/* "Why is this here?" preview narrative */}
              {item.whyIsThisHere && (
                <div className="mt-3 pt-3 border-t border-slate-100">
                  <div className="text-xs text-slate-600 bg-slate-50 p-3 rounded-lg border border-slate-100">
                    <span className="font-semibold text-slate-800 font-mono text-[11px] uppercase block mb-1">
                      Why is this here?
                    </span>
                    <p className="leading-relaxed">
                      {item.whyIsThisHere.whyUsed} {item.whyIsThisHere.relevantChemistry}
                    </p>
                  </div>
                </div>
              )}

              {/* Action Button */}
              <div className="mt-3 flex items-center justify-between pt-1">
                <div className="flex items-center gap-2 text-[11px] text-slate-500">
                  <FileText className="w-3.5 h-3.5" />
                  <span>{item.evidenceIds.length} Cited Monograph{item.evidenceIds.length !== 1 ? 's' : ''}</span>
                </div>

                <button
                  onClick={() => onSelectIngredient(item, entity)}
                  className="px-3.5 py-1.5 bg-slate-900 hover:bg-slate-800 text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer shadow-2xs"
                >
                  <span>Why is this here? & Evidence</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
