import React from 'react';
import {
  X,
  ExternalLink,
  ShieldCheck,
  Globe,
  Database,
  Calendar,
  AlertTriangle,
  HelpCircle,
  FileText,
  Layers,
  Sparkles,
  CheckCircle2,
} from 'lucide-react';
import { WebResearchResult, FieldProvenance, VerificationStatus } from '../../types';

interface WebResearchProvenanceModalProps {
  ingredientName: string;
  research: WebResearchResult | null;
  verificationStatus?: VerificationStatus;
  onClose: () => void;
  onTriggerResearch?: () => void;
  isResearching?: boolean;
}

export const WebResearchProvenanceModal: React.FC<WebResearchProvenanceModalProps> = ({
  ingredientName,
  research,
  verificationStatus = 'UNRESOLVED_UNKNOWN',
  onClose,
  onTriggerResearch,
  isResearching = false,
}) => {
  const getBadgeStyle = (status: VerificationStatus) => {
    switch (status) {
      case 'LOCAL_VERIFIED':
        return 'bg-emerald-50 text-emerald-800 border-emerald-300';
      case 'VERIFIED_WEB_BACKED':
        return 'bg-indigo-50 text-indigo-900 border-indigo-300';
      case 'WEB_RESEARCHED_CANDIDATE':
        return 'bg-blue-50 text-blue-900 border-blue-300';
      default:
        return 'bg-amber-50 text-amber-900 border-amber-300';
    }
  };

  const getStatusLabel = (status: VerificationStatus) => {
    switch (status) {
      case 'LOCAL_VERIFIED':
        return 'LOCAL VERIFIED RECORD';
      case 'VERIFIED_WEB_BACKED':
        return 'VERIFIED FROM SOURCES';
      case 'WEB_RESEARCHED_CANDIDATE':
        return 'WEB-RESEARCHED CANDIDATE';
      default:
        return 'UNKNOWN / INSUFFICIENT EVIDENCE';
    }
  };

  const getSourceTypeLabel = (type: string) => {
    switch (type) {
      case 'government_regulatory':
        return 'Government / Regulatory Agency (EFSA/FDA/WHO)';
      case 'official_standards':
        return 'Official Standards Organization (Codex/ISO)';
      case 'scientific_database':
        return 'Curated Scientific Database (PubChem/CAS)';
      case 'peer_reviewed_literature':
        return 'Peer-Reviewed Scientific Literature';
      case 'manufacturer_technical':
        return 'Manufacturer Technical Specification';
      default:
        return 'Reputable Scientific Web Source';
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-3 sm:p-4 overflow-y-auto">
      <div className="bg-white border border-slate-200 rounded-2xl shadow-xl w-full max-w-2xl max-h-[90vh] flex flex-col overflow-hidden">
        {/* Modal Header */}
        <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between gap-3 bg-slate-50/70">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono text-xs font-semibold text-slate-500 uppercase tracking-wide">
              Scientific Evidence Provenance
            </span>
            <span>·</span>
            <span
              className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded border uppercase ${getBadgeStyle(
                research?.verificationStatus || verificationStatus
              )}`}
            >
              {getStatusLabel(research?.verificationStatus || verificationStatus)}
            </span>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="p-1 text-slate-400 hover:text-slate-700 hover:bg-slate-200/60 rounded-lg transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-5 sm:p-6 overflow-y-auto space-y-6 text-xs text-slate-700">
          {/* Main Title & Status */}
          <div>
            <h2 className="text-xl font-bold text-slate-900">
              {research?.canonicalName || ingredientName}
            </h2>
            <p className="text-xs text-slate-500 mt-0.5 font-mono">
              Label Declaration: "{ingredientName}"
              {research?.identifier && ` · Statutory Code: ${research.identifier}`}
            </p>
          </div>

          {/* Research State / Unknown Callout */}
          {(!research || research.verificationStatus === 'UNRESOLVED_UNKNOWN') && (
            <div className="p-4 bg-amber-50/80 border border-amber-200 rounded-xl space-y-2">
              <div className="flex items-start gap-2 text-amber-900 font-semibold">
                <AlertTriangle className="w-4 h-4 text-amber-700 shrink-0 mt-0.5" />
                <span>Unknown / Insufficient Evidence</span>
              </div>
              <p className="text-amber-800 leading-relaxed">
                {research?.insufficientEvidenceReason ||
                  'LabelLens could not establish a sufficiently reliable chemical identity from the available label text and web evidence.'}
              </p>
              <div className="text-[11px] text-amber-700 font-mono">
                Physical chemistry principle: Never invent chemical structures or force formulas onto ambiguous composites or umbrella trade terms.
              </div>
              {onTriggerResearch && (
                <div className="pt-2">
                  <button
                    type="button"
                    disabled={isResearching}
                    onClick={onTriggerResearch}
                    className="px-3.5 py-1.5 bg-slate-900 hover:bg-slate-800 text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer shadow-xs disabled:opacity-50"
                  >
                    <Sparkles className="w-3.5 h-3.5 text-blue-400" />
                    <span>{isResearching ? 'Searching Google Grounding...' : 'Perform Google Search Grounding Research'}</span>
                  </button>
                </div>
              )}
            </div>
          )}

          {/* If Web Research Data is Present */}
          {research && (
            <>
              {/* Summary Card */}
              <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl space-y-2">
                <span className="text-[11px] font-mono font-semibold text-slate-600 uppercase block">
                  Authoritative Scientific Identity
                </span>
                <p className="text-sm font-medium text-slate-900 leading-relaxed">
                  {research.summary}
                </p>
                <div className="pt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-slate-600 text-[11px]">
                  <span>
                    Classification:{' '}
                    <strong className="text-slate-900">{research.chemicalClass}</strong>
                  </span>
                  <span>·</span>
                  <span>
                    Role:{' '}
                    <strong className="text-slate-900">{research.functionalRole}</strong>
                  </span>
                  <span>·</span>
                  <span>
                    Representation:{' '}
                    <strong className="text-slate-900">{research.representationType}</strong>
                  </span>
                </div>
              </div>

              {/* Chemical Constants Grid (Showing Nulls explicitly for Mixtures) */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                <div className="p-3 bg-white border border-slate-200 rounded-xl">
                  <span className="text-[10px] font-mono text-slate-500 uppercase block">
                    Chemical Formula
                  </span>
                  <span className="text-xs font-mono font-bold text-slate-900 mt-1 block">
                    {research.chemicalFormula || 'None (Mixture)'}
                  </span>
                </div>

                <div className="p-3 bg-white border border-slate-200 rounded-xl">
                  <span className="text-[10px] font-mono text-slate-500 uppercase block">
                    Molecular Weight
                  </span>
                  <span className="text-xs font-mono font-bold text-slate-900 mt-1 block">
                    {research.molecularWeight ? `${research.molecularWeight} g/mol` : 'None (Distributed)'}
                  </span>
                </div>

                <div className="p-3 bg-white border border-slate-200 rounded-xl">
                  <span className="text-[10px] font-mono text-slate-500 uppercase block">
                    CAS Registry Number
                  </span>
                  <span className="text-xs font-mono font-bold text-slate-900 mt-1 block">
                    {research.casNumber || 'None'}
                  </span>
                </div>

                <div className="p-3 bg-white border border-slate-200 rounded-xl">
                  <span className="text-[10px] font-mono text-slate-500 uppercase block">
                    Confidence Level
                  </span>
                  <span className="text-xs font-mono font-bold text-emerald-800 mt-1 block">
                    {research.confidenceLevel} ({research.confidenceScore}%)
                  </span>
                </div>
              </div>

              {/* Technical Function & Chemistry */}
              <div className="space-y-3 bg-white p-4 border border-slate-200 rounded-xl">
                <div>
                  <h4 className="font-semibold text-slate-900 text-xs font-mono uppercase text-slate-600 mb-1">
                    Why Is This Used?
                  </h4>
                  <p className="leading-relaxed text-slate-700">{research.whyUsed}</p>
                </div>
                <div>
                  <h4 className="font-semibold text-slate-900 text-xs font-mono uppercase text-slate-600 mb-1">
                    Physical Chemistry Mechanism
                  </h4>
                  <p className="leading-relaxed text-slate-700">{research.relevantChemistry}</p>
                </div>
                <div>
                  <h4 className="font-semibold text-slate-900 text-xs font-mono uppercase text-slate-600 mb-1">
                    Regulatory Evidence Support
                  </h4>
                  <p className="leading-relaxed text-slate-700">{research.evidenceSupport}</p>
                </div>
              </div>

              {/* Grounded Web Sources List (Requirement 3: Priority to official bodies) */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <h3 className="font-mono text-xs font-bold text-slate-900 uppercase">
                    Grounded Web Sources ({research.sources.length})
                  </h3>
                  <span className="text-[11px] text-slate-500 font-mono">
                    Retrieved: {new Date(research.searchedAt).toLocaleTimeString()}
                  </span>
                </div>

                <div className="space-y-1.5">
                  {research.sources.map((src, idx) => (
                    <a
                      key={idx}
                      href={src.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="p-3 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-lg flex items-start justify-between gap-3 group transition-colors"
                    >
                      <div className="space-y-0.5">
                        <div className="flex items-center gap-2">
                          <Globe className="w-3.5 h-3.5 text-blue-600 shrink-0" />
                          <span className="font-semibold text-slate-900 group-hover:text-blue-700 transition-colors">
                            {src.title}
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-500 font-mono truncate max-w-md">
                          {src.url}
                        </p>
                        <span className="inline-block text-[10px] font-mono px-1.5 py-0.2 bg-white text-slate-600 rounded border border-slate-200">
                          {getSourceTypeLabel(src.sourceType)}
                        </span>
                      </div>

                      <ExternalLink className="w-3.5 h-3.5 text-slate-400 group-hover:text-slate-700 shrink-0 mt-1" />
                    </a>
                  ))}
                </div>
              </div>

              {/* Field-by-Field Provenance Table (Requirement 7) */}
              {research.provenance && research.provenance.length > 0 && (
                <div className="space-y-2 pt-2">
                  <h3 className="font-mono text-xs font-bold text-slate-900 uppercase">
                    Field-Level Verification Audit
                  </h3>

                  <div className="border border-slate-200 rounded-xl overflow-hidden divide-y divide-slate-100 bg-white">
                    {research.provenance.map((prov, pIdx) => (
                      <div key={pIdx} className="p-3 space-y-1">
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-mono font-semibold text-slate-800">
                            {prov.field}
                          </span>
                          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-50 text-emerald-800 border border-emerald-200">
                            Confidence: {Math.round(prov.confidence * 100)}%
                          </span>
                        </div>
                        <div className="text-xs text-slate-900 font-medium">
                          Value: {String(prov.value || 'null')}
                        </div>
                        {prov.evidenceText && (
                          <p className="text-[11px] text-slate-600 italic bg-slate-50 p-2 rounded border border-slate-100">
                            "{prov.evidenceText}"
                          </p>
                        )}
                        <div className="text-[10px] text-slate-500 flex items-center gap-2 pt-0.5">
                          <span>Source: {prov.sourceTitle || prov.sourceUrl || 'Official Monograph'}</span>
                          <span>·</span>
                          <span>Type: {getSourceTypeLabel(prov.sourceType)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Modal Footer */}
        <div className="px-5 py-3 border-t border-slate-100 bg-slate-50 flex items-center justify-between gap-3">
          <div className="text-[11px] text-slate-500">
            Grounding engine: Gemini Vision + Google Search Grounding API
          </div>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 bg-slate-900 text-white rounded-lg text-xs font-semibold hover:bg-slate-800 cursor-pointer"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
