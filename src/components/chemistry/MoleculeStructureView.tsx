import React from 'react';
import { ChemicalEntity } from '../../types';

interface MoleculeStructureViewProps {
  entity: ChemicalEntity | null;
  className?: string;
}

export const MoleculeStructureView: React.FC<MoleculeStructureViewProps> = ({ entity, className = '' }) => {
  if (!entity) {
    return (
      <div className={`p-6 bg-slate-50 border border-slate-200 rounded-xl text-center ${className}`}>
        <p className="text-xs uppercase font-mono text-slate-600 tracking-wider">Unresolved Entity</p>
        <p className="text-sm text-slate-700 mt-1">
          No discrete molecular structure available. Substance is an ambiguous or composite formulation component.
        </p>
      </div>
    );
  }

  // Complex mixture or unresolved
  if (
    entity.representationType === 'Complex natural mixture / extract' ||
    entity.representationType === 'Polymer / biological mixture' ||
    entity.representationType === 'Unresolved botanical / flavour' ||
    entity.structureSvgType === 'none'
  ) {
    return (
      <div className={`p-6 bg-slate-50 border border-slate-200 rounded-xl ${className}`}>
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-lg bg-amber-50 border border-amber-200 text-amber-700 flex items-center justify-center shrink-0 font-mono text-sm">
            Δ
          </div>
          <div>
            <h4 className="text-sm font-semibold text-slate-900">
              Multi-Constituent Matrix — No Single Discrete Structure
            </h4>
            <p className="text-xs text-slate-600 mt-1 leading-relaxed">
              {entity.preferredName} is classified as a <strong className="font-medium text-slate-800">{entity.representationType.toLowerCase()}</strong>.
              It comprises an ensemble of biomolecules (proteins, polysaccharides, or volatile terpenes) rather than a uniform molecular formula.
            </p>
            <div className="mt-3 p-2.5 bg-white border border-slate-200 rounded-lg text-xs text-slate-600">
              <span className="font-semibold text-slate-700">Scientific principle:</span> Forcing a single molecular structure onto a biological mixture violates chemical truth.
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Clean, scientifically accurate vector renderings of defined entities
  return (
    <div className={`bg-white border border-slate-200 rounded-xl p-5 ${className}`}>
      <div className="flex items-center justify-between pb-3 border-b border-slate-100 mb-4">
        <div>
          <span className="text-[11px] font-mono uppercase tracking-wider text-slate-600">
            2D Chemical Topology
          </span>
          <h4 className="text-sm font-semibold text-slate-900">{entity.preferredName}</h4>
        </div>
        <span className="text-xs font-mono px-2 py-0.5 bg-slate-100 text-slate-700 rounded">
          {entity.formula || 'Empirical'}
        </span>
      </div>

      <div className="flex items-center justify-center py-4 bg-slate-50/50 rounded-lg border border-slate-100">
        {entity.structureSvgType === 'sucrose' && (
          <svg viewBox="0 0 340 180" className="w-full max-w-[280px] h-auto stroke-slate-800" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            {/* Sucrose: Glucopyranosyl ring */}
            <polygon points="60,80 90,55 130,65 140,105 105,130 70,115" className="fill-white stroke-slate-800" strokeWidth="2.2" />
            <text x="50" y="85" className="text-[10px] font-mono fill-slate-700 font-semibold" stroke="none">HO</text>
            <text x="85" y="45" className="text-[10px] font-mono fill-slate-700 font-semibold" stroke="none">OH</text>
            <text x="60" y="138" className="text-[10px] font-mono fill-slate-700 font-semibold" stroke="none">HOCH₂</text>
            {/* Glycosidic Bridge Oxygen */}
            <line x1="140" y1="105" x2="165" y2="90" strokeWidth="2.2" />
            <circle cx="172" cy="85" r="7" className="fill-blue-50 stroke-blue-600" />
            <text x="168" y="89" className="text-[10px] font-mono fill-blue-700 font-bold" stroke="none">O</text>
            <line x1="179" y1="90" x2="200" y2="105" strokeWidth="2.2" />
            {/* Fructofuranosyl ring */}
            <polygon points="200,105 210,65 245,55 265,90 240,120" className="fill-white stroke-slate-800" strokeWidth="2.2" />
            <text x="270" y="95" className="text-[10px] font-mono fill-slate-700 font-semibold" stroke="none">CH₂OH</text>
            <text x="245" y="48" className="text-[10px] font-mono fill-slate-700 font-semibold" stroke="none">OH</text>
            <text x="235" y="136" className="text-[10px] font-mono fill-slate-700 font-semibold" stroke="none">HO</text>
          </svg>
        )}

        {entity.structureSvgType === 'caffeine' && (
          <svg viewBox="0 0 280 180" className="w-full max-w-[240px] h-auto stroke-slate-800" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            {/* Pyrimidine ring */}
            <polygon points="90,50 140,50 165,90 140,130 90,130 65,90" className="fill-white stroke-slate-800" strokeWidth="2" />
            {/* Carbonyls */}
            <line x1="90" y1="50" x2="80" y2="25" strokeWidth="2" />
            <line x1="86" y1="52" x2="76" y2="27" strokeWidth="1.5" />
            <text x="68" y="20" className="text-[10px] font-mono fill-rose-600 font-bold" stroke="none">=O</text>
            
            <line x1="140" y1="130" x2="150" y2="155" strokeWidth="2" />
            <text x="150" y="166" className="text-[10px] font-mono fill-rose-600 font-bold" stroke="none">=O</text>

            {/* Imidazole fused ring */}
            <polygon points="140,50 185,60 195,95 165,90" className="fill-white stroke-slate-800" strokeWidth="2" />
            {/* Methyls & Nitrogens */}
            <text x="50" y="95" className="text-[10px] font-mono fill-blue-600 font-bold" stroke="none">N-CH₃</text>
            <text x="135" y="48" className="text-[10px] font-mono fill-blue-600 font-bold" stroke="none">N</text>
            <text x="188" y="58" className="text-[10px] font-mono fill-blue-600 font-bold" stroke="none">N</text>
            <text x="125" y="142" className="text-[10px] font-mono fill-blue-600 font-bold" stroke="none">N-CH₃</text>
          </svg>
        )}

        {entity.structureSvgType === 'glycerol' && (
          <svg viewBox="0 0 260 140" className="w-full max-w-[220px] h-auto stroke-slate-800" fill="none" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            {/* Propane backbone */}
            <polyline points="50,85 100,55 150,85 200,55" strokeWidth="2.5" />
            {/* Hydroxyl branches */}
            <line x1="50" y1="85" x2="30" y2="95" strokeWidth="2" />
            <text x="10" y="108" className="text-[11px] font-mono fill-slate-700 font-bold" stroke="none">HO</text>

            <line x1="100" y1="55" x2="100" y2="25" strokeWidth="2" />
            <text x="92" y="20" className="text-[11px] font-mono fill-slate-700 font-bold" stroke="none">OH</text>

            <line x1="200" y1="55" x2="225" y2="70" strokeWidth="2" />
            <text x="230" y="76" className="text-[11px] font-mono fill-slate-700 font-bold" stroke="none">OH</text>
          </svg>
        )}

        {entity.structureSvgType === 'citric_acid' && (
          <svg viewBox="0 0 300 160" className="w-full max-w-[260px] h-auto stroke-slate-800" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            {/* Glutarate skeleton */}
            <polyline points="60,95 105,65 150,95 195,65 240,95" strokeWidth="2.5" />
            {/* Left Carboxyl */}
            <text x="25" y="105" className="text-[10px] font-mono fill-rose-600 font-bold" stroke="none">HOOC-</text>
            {/* Right Carboxyl */}
            <text x="245" y="100" className="text-[10px] font-mono fill-rose-600 font-bold" stroke="none">-COOH</text>
            {/* Center -OH and -COOH */}
            <line x1="150" y1="95" x2="150" y2="130" strokeWidth="2" />
            <text x="140" y="145" className="text-[10px] font-mono fill-slate-700 font-bold" stroke="none">OH</text>
            <line x1="150" y1="95" x2="150" y2="55" strokeWidth="2" />
            <text x="135" y="48" className="text-[10px] font-mono fill-rose-600 font-bold" stroke="none">COOH</text>
          </svg>
        )}

        {entity.structureSvgType === 'sodium_chloride' && (
          <div className="flex flex-col items-center gap-2 py-2">
            <svg viewBox="0 0 200 140" className="w-48 h-32" fill="none">
              {/* 3D Ionic Lattice Unit */}
              <rect x="40" y="40" width="80" height="80" className="stroke-slate-300 stroke-1 fill-none" />
              <rect x="70" y="20" width="80" height="80" className="stroke-slate-300 stroke-1 fill-none" />
              <line x1="40" y1="40" x2="70" y2="20" className="stroke-slate-300 stroke-1" />
              <line x1="120" y1="40" x2="150" y2="20" className="stroke-slate-300 stroke-1" />
              <line x1="40" y1="120" x2="70" y2="100" className="stroke-slate-300 stroke-1" />
              <line x1="120" y1="120" x2="150" y2="100" className="stroke-slate-300 stroke-1" />
              
              {/* Na+ (blue) & Cl- (emerald) ions */}
              <circle cx="40" cy="40" r="8" className="fill-blue-600" />
              <circle cx="120" cy="40" r="12" className="fill-emerald-600" />
              <circle cx="40" cy="120" r="12" className="fill-emerald-600" />
              <circle cx="120" cy="120" r="8" className="fill-blue-600" />
              <circle cx="70" cy="20" r="12" className="fill-emerald-600" />
              <circle cx="150" cy="20" r="8" className="fill-blue-600" />
              <circle cx="150" cy="100" r="12" className="fill-emerald-600" />
            </svg>
            <div className="flex items-center gap-4 text-xs font-mono text-slate-600">
              <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-blue-600"></span>Na⁺ (Sodium cation)</span>
              <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-emerald-600"></span>Cl⁻ (Chloride anion)</span>
            </div>
          </div>
        )}

        {entity.structureSvgType === 'zinc_oxide' && (
          <div className="flex flex-col items-center gap-2 py-2">
            <svg viewBox="0 0 200 130" className="w-44 h-28" fill="none">
              {/* Hexagonal wurtzite coordination */}
              <polygon points="100,20 150,45 150,95 100,120 50,95 50,45" className="stroke-slate-300 stroke-1 fill-none" />
              <circle cx="100" cy="20" r="9" className="fill-indigo-600" />
              <circle cx="150" cy="45" r="11" className="fill-rose-500" />
              <circle cx="150" cy="95" r="9" className="fill-indigo-600" />
              <circle cx="100" cy="120" r="11" className="fill-rose-500" />
              <circle cx="50" cy="95" r="9" className="fill-indigo-600" />
              <circle cx="50" cy="45" r="11" className="fill-rose-500" />
              <circle cx="100" cy="70" r="10" className="fill-indigo-600" />
            </svg>
            <div className="flex items-center gap-4 text-xs font-mono text-slate-600">
              <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-indigo-600"></span>Zn²⁺ (Zinc)</span>
              <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-rose-500"></span>O²⁻ (Oxide)</span>
            </div>
          </div>
        )}

        {entity.structureSvgType === 'lecithin' && (
          <div className="flex flex-col items-center w-full px-4 py-2">
            <div className="w-full text-center text-xs text-slate-600 mb-2">
              Representative Phosphatidylcholine Scaffold (R₁, R₂ = variable C16–C18 fatty acyl chains)
            </div>
            <svg viewBox="0 0 280 120" className="w-full max-w-[260px] h-auto stroke-slate-800" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              {/* Polar head */}
              <circle cx="50" cy="60" r="22" className="fill-blue-50 stroke-blue-600 stroke-2" />
              <text x="35" y="58" className="text-[9px] font-mono fill-blue-700 font-bold" stroke="none">Choline</text>
              <text x="34" y="69" className="text-[9px] font-mono fill-blue-700 font-bold" stroke="none">Phosphate</text>
              
              {/* Glycerol spine */}
              <line x1="72" y1="60" x2="110" y2="60" strokeWidth="2" />
              <rect x="110" y="35" width="22" height="50" rx="3" className="fill-slate-100 stroke-slate-600" />
              <text x="114" y="63" className="text-[8px] font-mono fill-slate-700" stroke="none">Glyc</text>
              
              {/* Dual hydrophobic hydrocarbon tails */}
              <path d="M132,45 L150,38 L168,45 L186,38 L204,45 L222,38 L240,45" strokeWidth="2" />
              <text x="245" y="47" className="text-[9px] font-mono fill-slate-500" stroke="none">R₁</text>

              <path d="M132,75 L150,68 L168,75 L186,68 L204,75 L222,68 L240,75" strokeWidth="2" />
              <text x="245" y="77" className="text-[9px] font-mono fill-slate-500" stroke="none">R₂</text>
            </svg>
            <div className="flex items-center justify-between w-full text-[11px] font-mono text-slate-500 mt-2 pt-2 border-t border-slate-100">
              <span>Polar Hydrophilic Head</span>
              <span>Non-Polar Lipophilic Tails</span>
            </div>
          </div>
        )}
      </div>

      <div className="mt-3 pt-3 border-t border-slate-100 flex flex-wrap items-center justify-between gap-2 text-xs font-mono text-slate-600">
        <span>CAS: <strong className="text-slate-800">{entity.cas || 'Not assigned'}</strong></span>
        <span>MW: <strong className="text-slate-800">{entity.molecularWeight ? `${entity.molecularWeight} g/mol` : 'Polydisperse / Variable'}</strong></span>
      </div>
    </div>
  );
};
