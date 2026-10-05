import React from 'react';
import { Camera, Scale, Search, BookOpen, Layers } from 'lucide-react';

export type NavTab = 'home' | 'scan' | 'compare' | 'catalog' | 'learn';

interface HeaderProps {
  currentTab: NavTab;
  onTabChange: (tab: NavTab) => void;
}

export const Header: React.FC<HeaderProps> = ({ currentTab, onTabChange }) => {
  return (
    <>
      {/* Desktop & Mobile Top Bar adhering strictly to 3-zone contract */}
      <header className="sticky top-0 z-30 bg-white/95 backdrop-blur-md border-b border-slate-200">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
          {/* Zone 1: Single text element wordmark */}
          <button
            onClick={() => onTabChange('home')}
            className="flex items-center gap-2 text-left cursor-pointer group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 rounded"
          >
            <span className="w-7 h-7 rounded-lg bg-slate-900 text-white flex items-center justify-center font-mono font-bold text-xs tracking-tighter">
              LL
            </span>
            <span className="text-base sm:text-lg font-bold tracking-tight text-slate-900 group-hover:text-blue-600 transition-colors">
              LabelLens
            </span>
          </button>

          {/* Zone 2: 4-6 clean text navigation links */}
          <nav className="hidden md:flex items-center gap-8 text-sm font-medium text-slate-600">
            <button
              onClick={() => onTabChange('scan')}
              className={`hover:text-slate-900 transition-colors cursor-pointer py-1 ${
                currentTab === 'scan' ? 'text-slate-900 border-b-2 border-slate-900 font-semibold' : ''
              }`}
            >
              Scan
            </button>
            <button
              onClick={() => onTabChange('compare')}
              className={`hover:text-slate-900 transition-colors cursor-pointer py-1 ${
                currentTab === 'compare' ? 'text-slate-900 border-b-2 border-slate-900 font-semibold' : ''
              }`}
            >
              Compare
            </button>
            <button
              onClick={() => onTabChange('catalog')}
              className={`hover:text-slate-900 transition-colors cursor-pointer py-1 ${
                currentTab === 'catalog' ? 'text-slate-900 border-b-2 border-slate-900 font-semibold' : ''
              }`}
            >
              Catalog
            </button>
            <button
              onClick={() => onTabChange('learn')}
              className={`hover:text-slate-900 transition-colors cursor-pointer py-1 ${
                currentTab === 'learn' ? 'text-slate-900 border-b-2 border-slate-900 font-semibold' : ''
              }`}
            >
              Learn
            </button>
          </nav>

          {/* Zone 3: 1-2 primary actions */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => onTabChange('scan')}
              className="px-3.5 py-1.5 text-xs font-semibold text-white bg-slate-900 hover:bg-slate-800 active:scale-[0.98] transition-all rounded-lg flex items-center gap-1.5 shadow-sm whitespace-nowrap cursor-pointer"
            >
              <Camera className="w-3.5 h-3.5" />
              <span>Scan Label</span>
            </button>
          </div>
        </div>
      </header>

      {/* Mobile Fixed Bottom Navigation Bar (<15% viewport height for thumb zone) */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 z-40 bg-white/95 backdrop-blur-md border-t border-slate-200 safe-bottom">
        <div className="grid grid-cols-5 items-center h-14 px-2">
          <button
            onClick={() => onTabChange('home')}
            className={`flex flex-col items-center justify-center py-1 transition-colors ${
              currentTab === 'home' ? 'text-slate-900' : 'text-slate-600 hover:text-slate-800'
            }`}
          >
            <Layers className="w-5 h-5" />
            <span className="text-[10px] font-medium mt-0.5">Overview</span>
          </button>

          <button
            onClick={() => onTabChange('scan')}
            className={`flex flex-col items-center justify-center py-1 transition-colors ${
              currentTab === 'scan' ? 'text-blue-600 font-semibold' : 'text-slate-600 hover:text-slate-800'
            }`}
          >
            <Camera className="w-5 h-5" />
            <span className="text-[10px] font-medium mt-0.5">Scan</span>
          </button>

          <button
            onClick={() => onTabChange('compare')}
            className={`flex flex-col items-center justify-center py-1 transition-colors ${
              currentTab === 'compare' ? 'text-slate-900 font-semibold' : 'text-slate-600 hover:text-slate-800'
            }`}
          >
            <Scale className="w-5 h-5" />
            <span className="text-[10px] font-medium mt-0.5">Compare</span>
          </button>

          <button
            onClick={() => onTabChange('catalog')}
            className={`flex flex-col items-center justify-center py-1 transition-colors ${
              currentTab === 'catalog' ? 'text-slate-900 font-semibold' : 'text-slate-600 hover:text-slate-800'
            }`}
          >
            <Search className="w-5 h-5" />
            <span className="text-[10px] font-medium mt-0.5">Catalog</span>
          </button>

          <button
            onClick={() => onTabChange('learn')}
            className={`flex flex-col items-center justify-center py-1 transition-colors ${
              currentTab === 'learn' ? 'text-slate-900 font-semibold' : 'text-slate-600 hover:text-slate-800'
            }`}
          >
            <BookOpen className="w-5 h-5" />
            <span className="text-[10px] font-medium mt-0.5">Learn</span>
          </button>
        </div>
      </nav>
    </>
  );
};
