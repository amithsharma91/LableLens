import React from 'react';
import { AlertCircle } from 'lucide-react';

export const DemoDisclaimer: React.FC<{ className?: string }> = ({ className = '' }) => {
  return (
    <div className={`bg-slate-100/90 border-b border-slate-200/80 px-4 py-2 text-xs text-slate-600 ${className}`}>
      <div className="max-w-6xl mx-auto flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <AlertCircle className="w-3.5 h-3.5 text-slate-500 shrink-0" />
          <span>
            <strong className="font-semibold text-slate-700">Phase 1 prototype</strong> — chemistry and evidence shown here use curated demonstration data. Production analysis will validate records against authoritative sources.
          </span>
        </div>
        <span className="hidden sm:inline-block font-mono text-[11px] text-slate-600 shrink-0">
          Empirical Truth · Zero Bias
        </span>
      </div>
    </div>
  );
};
