import React, { useState } from 'react';
import { Search, ArrowRight, Filter, Atom, CheckCircle2, AlertCircle } from 'lucide-react';
import { ChemicalEntity, IngredientObservation } from '../types';
import { DEMO_CHEMICAL_ENTITIES } from '../data/chemicalEntities';
import { DEMO_PRODUCTS } from '../data/demoProducts';

interface SearchViewProps {
  onSelectEntity: (entity: ChemicalEntity, sampleObservation?: IngredientObservation) => void;
}

export const SearchView: React.FC<SearchViewProps> = ({ onSelectEntity }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedRepType, setSelectedRepType] = useState<string>('all');

  const entities = Object.values(DEMO_CHEMICAL_ENTITIES);

  const repTypes = Array.from(new Set(entities.map(e => e.representationType)));

  const filteredEntities = entities.filter(e => {
    const matchesSearch =
      searchTerm.trim() === '' ||
      e.preferredName.toLowerCase().includes(searchTerm.toLowerCase()) ||
      e.aliases.some(a => a.toLowerCase().includes(searchTerm.toLowerCase())) ||
      (e.formula && e.formula.toLowerCase().includes(searchTerm.toLowerCase())) ||
      (e.cas && e.cas.includes(searchTerm)) ||
      e.chemicalClass.toLowerCase().includes(searchTerm.toLowerCase());

    const matchesType =
      selectedRepType === 'all' || e.representationType === selectedRepType;

    return matchesSearch && matchesType;
  });

  // Find a sample observation from demo products if exists
  const handleItemClick = (entity: ChemicalEntity) => {
    let matchedObs: IngredientObservation | undefined;
    for (const prod of DEMO_PRODUCTS) {
      const found = prod.ingredients.find(i => i.chemicalEntityId === entity.id);
      if (found) {
        matchedObs = found;
        break;
      }
    }

    // If none found in products, make a synthetic observation for the detail view
    const obs: IngredientObservation = matchedObs || {
      id: `synth_${entity.id}`,
      rawText: entity.preferredName,
      normalizedText: entity.preferredName,
      matchStatus: 'Matched',
      chemicalEntityId: entity.id,
      role: entity.chemicalClass,
      confidence: 'High',
      confidenceScore: 98,
      evidenceIds: [],
      whyIsThisHere: {
        whatIsIt: `${entity.preferredName} (${entity.chemicalClass}).`,
        whyUsed: 'Curated reference entity within computational chemistry demo database.',
        relevantChemistry: entity.descriptors.join('. ') + '.',
        evidenceSupport: 'Indexed in authoritative demonstration registry.',
        uncertainties: entity.limitations || 'Specifications verified for demonstration prototype.'
      }
    };

    onSelectEntity(entity, obs);
  };

  return (
    <div className="max-w-5xl mx-auto px-4 py-6 space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2 text-xs font-mono text-slate-500 mb-1">
          <span>CURATED CHEMICAL CATALOG</span>
          <span>·</span>
          <span>DEMO REGISTRY</span>
        </div>
        <h1 className="text-2xl sm:text-3xl font-bold text-slate-900">
          Ingredient & Chemical Entity Index
        </h1>
        <p className="text-sm text-slate-600 mt-1 max-w-2xl">
          Search verified demonstration entities by scientific name, commercial synonym, molecular formula, or CAS number.
        </p>
      </div>

      {/* Search Input Bar */}
      <div className="relative">
        <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-3.5" />
        <input
          type="text"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          placeholder="Search by name (e.g. Sucrose, Zinc Oxide, Lecithin, Glycerol, 57-50-1)..."
          className="w-full pl-10 pr-4 py-2.5 bg-white border border-slate-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-slate-900 shadow-2xs"
        />
        {searchTerm && (
          <button
            onClick={() => setSearchTerm('')}
            className="absolute right-3.5 top-3 text-xs text-slate-400 hover:text-slate-600 cursor-pointer"
          >
            Clear
          </button>
        )}
      </div>

      {/* Filter Tabs by Representation Type */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1 text-xs">
        <span className="text-slate-600 font-mono text-[11px] uppercase shrink-0">Entity Type:</span>
        <button
          onClick={() => setSelectedRepType('all')}
          className={`px-3 py-1 rounded-md transition-colors cursor-pointer whitespace-nowrap ${
            selectedRepType === 'all'
              ? 'bg-slate-900 text-white font-medium'
              : 'bg-white text-slate-600 border border-slate-200 hover:text-slate-900'
          }`}
        >
          All Entities ({entities.length})
        </button>
        {repTypes.map(t => (
          <button
            key={t}
            onClick={() => setSelectedRepType(t)}
            className={`px-3 py-1 rounded-md transition-colors cursor-pointer whitespace-nowrap ${
              selectedRepType === t
                ? 'bg-slate-900 text-white font-medium'
                : 'bg-white text-slate-600 border border-slate-200 hover:text-slate-900'
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Results Count & Grid */}
      <div>
        <div className="flex items-center justify-between text-xs text-slate-500 mb-3">
          <span>Showing {filteredEntities.length} verified chemical record{filteredEntities.length !== 1 ? 's' : ''}</span>
          <span className="font-mono text-[11px]">Curated Demo Subset</span>
        </div>

        {filteredEntities.length === 0 ? (
          <div className="p-8 bg-white rounded-xl border border-slate-200 text-center space-y-2">
            <p className="text-sm font-semibold text-slate-800">No matching demo entity found</p>
            <p className="text-xs text-slate-500 max-w-sm mx-auto">
              In Phase 1, only curated demonstration entities are indexed. In Phase 2, this connects to PubChem, ECHA, and CIR.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {filteredEntities.map((ent) => {
              const hasDiscreteStructure = ent.structureSvgType && ent.structureSvgType !== 'none';

              return (
                <div
                  key={ent.id}
                  onClick={() => handleItemClick(ent)}
                  className="bg-white border border-slate-200 rounded-xl p-5 hover:border-slate-400 hover:shadow-2xs transition-all cursor-pointer flex flex-col justify-between"
                >
                  <div>
                    <div className="flex items-center justify-between gap-2 mb-1.5">
                      <span className="text-[11px] font-mono text-slate-600 uppercase tracking-tight">
                        {ent.chemicalClass}
                      </span>
                      <span className="text-[10px] font-mono px-2 py-0.5 bg-slate-100 text-slate-700 rounded">
                        {ent.representationType}
                      </span>
                    </div>

                    <h3 className="text-base font-bold text-slate-900">
                      {ent.preferredName}
                    </h3>

                    <div className="text-xs text-slate-600 mt-1 line-clamp-1">
                      Synonyms: {ent.aliases.slice(0, 3).join(', ')}
                    </div>

                    <div className="mt-4 pt-3 border-t border-slate-100 grid grid-cols-2 gap-2 text-xs font-mono">
                      <div>
                        <span className="text-[10px] text-slate-600 uppercase block">Formula</span>
                        <span className="text-slate-900 font-medium">
                          {ent.formula || 'Mixture / None'}
                        </span>
                      </div>
                      <div>
                        <span className="text-[10px] text-slate-600 uppercase block">CAS No.</span>
                        <span className="text-slate-900 font-medium">
                          {ent.cas || 'Not assigned'}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs">
                    <span className="text-slate-500">
                      {hasDiscreteStructure ? '✓ 2D Topology' : 'Ensemble / Matrix'}
                    </span>
                    <span className="text-slate-900 font-semibold flex items-center gap-1">
                      <span>View Monograph</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
