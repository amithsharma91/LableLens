import React, { useState } from 'react';
import { Scale, ArrowRight, Check, X, ShieldAlert, FileText, Sparkles, Layers } from 'lucide-react';
import { Product, IngredientObservation, ChemicalEntity } from '../types';
import { DEMO_PRODUCTS } from '../data/demoProducts';
import { DEMO_CHEMICAL_ENTITIES } from '../data/chemicalEntities';

interface CompareViewProps {
  initialProductA?: Product;
  initialProductB?: Product;
  onInspectIngredient?: (obs: IngredientObservation, entity: ChemicalEntity | null) => void;
}

export const CompareView: React.FC<CompareViewProps> = ({
  initialProductA,
  initialProductB,
  onInspectIngredient,
}) => {
  const [productAId, setProductAId] = useState<string>(
    initialProductA?.id || DEMO_PRODUCTS[0].id // Artisanal Hazelnut Cocoa Spread
  );
  const [productBId, setProductBId] = useState<string>(
    initialProductB?.id || DEMO_PRODUCTS[1].id // Organic Dark Hazelnut Spread
  );

  const productA = DEMO_PRODUCTS.find(p => p.id === productAId) || DEMO_PRODUCTS[0];
  const productB = DEMO_PRODUCTS.find(p => p.id === productBId) || DEMO_PRODUCTS[1];

  // Helper to extract clean name tokens for matching
  const getNormalizedKey = (ing: IngredientObservation) => {
    return ing.chemicalEntityId || ing.normalizedText.toLowerCase().replace(/[()0-9%]/g, '').trim();
  };

  const keysA = new Map(productA.ingredients.map(i => [getNormalizedKey(i), i]));
  const keysB = new Map(productB.ingredients.map(i => [getNormalizedKey(i), i]));

  // Shared ingredients
  const sharedKeys = Array.from(keysA.keys()).filter(k => keysB.has(k));
  const sharedIngredients = sharedKeys.map(k => ({
    key: k,
    obsA: keysA.get(k)!,
    obsB: keysB.get(k)!,
    entity: keysA.get(k)?.chemicalEntityId ? DEMO_CHEMICAL_ENTITIES[keysA.get(k)!.chemicalEntityId!] : null,
  }));

  // Unique to A
  const uniqueToA = Array.from(keysA.entries())
    .filter(([k]) => !keysB.has(k))
    .map(([, v]) => v);

  // Unique to B
  const uniqueToB = Array.from(keysB.entries())
    .filter(([k]) => !keysA.has(k))
    .map(([, v]) => v);

  // Role category counts
  const allRoles = Array.from(
    new Set([
      ...productA.ingredients.map(i => i.role),
      ...productB.ingredients.map(i => i.role),
    ])
  );

  return (
    <div className="max-w-5xl mx-auto px-4 py-6 space-y-8">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2 text-xs font-mono text-slate-500 mb-1">
          <span>FORMULATION COMPARATIVE ANALYSIS</span>
          <span>·</span>
          <span>EMPIRICAL CROSS-EXAMINATION</span>
        </div>
        <h1 className="text-2xl sm:text-3xl font-bold text-slate-900">
          Compare Formulations
        </h1>
        <p className="text-sm text-slate-600 mt-1 max-w-3xl">
          Evaluate shared chemical ingredients, unique functional agents, and evidence availability side-by-side.
          LabelLens never assigns a subjective "winner" or arbitrary health grade.
        </p>
      </div>

      {/* Product Selectors */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Selector A */}
        <div className="bg-white p-4 rounded-xl border border-slate-200 space-y-2">
          <label className="block text-[11px] font-mono text-slate-500 uppercase">
            Product Formulation A
          </label>
          <select
            value={productAId}
            onChange={(e) => setProductAId(e.target.value)}
            className="w-full text-sm font-semibold p-2 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-900"
          >
            {DEMO_PRODUCTS.map(p => (
              <option key={p.id} value={p.id}>
                {p.name} ({p.domain})
              </option>
            ))}
          </select>
          <div className="text-xs text-slate-500 pt-1 flex items-center justify-between">
            <span>{productA.brand}</span>
            <span>
              {productA.ingredientsTree && productA.ingredientsTree.length > 0
                ? `${productA.ingredientsTree.length} primary (${productA.ingredients.length} total)`
                : `${productA.ingredients.length} components`}
            </span>
          </div>
        </div>

        {/* Selector B */}
        <div className="bg-white p-4 rounded-xl border border-slate-200 space-y-2">
          <label className="block text-[11px] font-mono text-slate-500 uppercase">
            Product Formulation B
          </label>
          <select
            value={productBId}
            onChange={(e) => setProductBId(e.target.value)}
            className="w-full text-sm font-semibold p-2 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-900"
          >
            {DEMO_PRODUCTS.map(p => (
              <option key={p.id} value={p.id}>
                {p.name} ({p.domain})
              </option>
            ))}
          </select>
          <div className="text-xs text-slate-500 pt-1 flex items-center justify-between">
            <span>{productB.brand}</span>
            <span>
              {productB.ingredientsTree && productB.ingredientsTree.length > 0
                ? `${productB.ingredientsTree.length} primary (${productB.ingredients.length} total)`
                : `${productB.ingredients.length} components`}
            </span>
          </div>
        </div>
      </div>

      {/* Dispassionate Scientific Disclaimer: Never declare a "winner" */}
      <div className="p-4 bg-slate-100 rounded-xl border border-slate-200 text-xs text-slate-700 flex items-start gap-2.5">
        <Scale className="w-4 h-4 text-slate-600 shrink-0 mt-0.5" />
        <div>
          <strong className="font-semibold text-slate-900">Zero-Bias Comparative Principle:</strong>
          <span className="ml-1 text-slate-600">
            Formulation choices involve technical trade-offs (e.g. microbial shelf stability vs short-shelf botanical extracts, or emulsifier type vs cost and rheology).
            LabelLens maps the chemistry without simplistic "healthier" or "better" scoring.
          </span>
        </div>
      </div>

      {/* Ingredient Overlap Summary */}
      <div className="grid grid-cols-3 gap-3 text-center">
        <div className="bg-white p-4 rounded-xl border border-slate-200">
          <span className="text-[11px] font-mono text-slate-600 uppercase block">Shared Ingredients</span>
          <span className="text-2xl font-bold font-mono text-slate-900 mt-1 block">
            {sharedIngredients.length}
          </span>
          <span className="text-[11px] text-slate-600 mt-0.5 block">Present in both products</span>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200">
          <span className="text-[11px] font-mono text-slate-600 uppercase block">Unique to A</span>
          <span className="text-2xl font-bold font-mono text-blue-700 mt-1 block">
            {uniqueToA.length}
          </span>
          <span className="text-[11px] text-slate-600 mt-0.5 block truncate">{productA.name}</span>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200">
          <span className="text-[11px] font-mono text-slate-600 uppercase block">Unique to B</span>
          <span className="text-2xl font-bold font-mono text-indigo-700 mt-1 block">
            {uniqueToB.length}
          </span>
          <span className="text-[11px] text-slate-600 mt-0.5 block truncate">{productB.name}</span>
        </div>
      </div>

      {/* Shared Ingredients Section */}
      <section className="bg-white rounded-2xl border border-slate-200 p-6 space-y-4">
        <div className="border-b border-slate-100 pb-3">
          <span className="text-xs font-mono uppercase tracking-wider text-slate-600">
            Consensus Composition
          </span>
          <h3 className="text-lg font-bold text-slate-900">
            Shared Chemical Ingredients ({sharedIngredients.length})
          </h3>
        </div>

        <div className="divide-y divide-slate-100">
          {sharedIngredients.map(({ key, obsA, obsB, entity }) => (
            <div key={key} className="py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
              <div>
                <h4 className="font-bold text-slate-900 text-sm">
                  {entity ? entity.preferredName : obsA.normalizedText}
                </h4>
                <div className="flex items-center gap-3 text-slate-500 mt-0.5">
                  <span>In A: "{obsA.rawText}"</span>
                  <span>·</span>
                  <span>In B: "{obsB.rawText}"</span>
                </div>
              </div>

              <div className="flex items-center gap-3 text-right shrink-0">
                <span className="font-mono text-slate-600">
                  {entity?.formula || 'Mixture'}
                </span>
                <span className="px-2 py-0.5 bg-slate-100 text-slate-700 rounded font-mono text-[11px]">
                  {obsA.role}
                </span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Side-by-Side Unique Ingredients */}
      <section className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Unique to Product A */}
        <div className="bg-white rounded-2xl border border-slate-200 p-5 space-y-3">
          <div className="border-b border-slate-100 pb-2">
            <span className="text-[11px] font-mono text-blue-700 uppercase font-semibold">
              Distinct to Product A
            </span>
            <h4 className="text-base font-bold text-slate-900 truncate">
              {productA.name} ({uniqueToA.length})
            </h4>
          </div>

          {uniqueToA.length === 0 ? (
            <p className="text-xs text-slate-500 py-4 text-center">No unique ingredients.</p>
          ) : (
            <div className="space-y-2.5">
              {uniqueToA.map((ing) => (
                <div key={ing.id} className="p-3 bg-slate-50 rounded-lg border border-slate-200 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-slate-900">{ing.normalizedText}</span>
                    <span className="font-mono text-[11px] text-slate-500">{ing.matchStatus}</span>
                  </div>
                  <p className="text-slate-600 mt-1">Role: {ing.role}</p>
                  {ing.whyIsThisHere && (
                    <p className="text-[11px] text-slate-500 mt-1 italic">
                      "{ing.whyIsThisHere.whyUsed}"
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Unique to Product B */}
        <div className="bg-white rounded-2xl border border-slate-200 p-5 space-y-3">
          <div className="border-b border-slate-100 pb-2">
            <span className="text-[11px] font-mono text-indigo-700 uppercase font-semibold">
              Distinct to Product B
            </span>
            <h4 className="text-base font-bold text-slate-900 truncate">
              {productB.name} ({uniqueToB.length})
            </h4>
          </div>

          {uniqueToB.length === 0 ? (
            <p className="text-xs text-slate-500 py-4 text-center">No unique ingredients.</p>
          ) : (
            <div className="space-y-2.5">
              {uniqueToB.map((ing) => (
                <div key={ing.id} className="p-3 bg-slate-50 rounded-lg border border-slate-200 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-slate-900">{ing.normalizedText}</span>
                    <span className="font-mono text-[11px] text-slate-500">{ing.matchStatus}</span>
                  </div>
                  <p className="text-slate-600 mt-1">Role: {ing.role}</p>
                  {ing.whyIsThisHere && (
                    <p className="text-[11px] text-slate-500 mt-1 italic">
                      "{ing.whyIsThisHere.whyUsed}"
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      {/* Role & Functional Differences Table */}
      <section className="bg-white rounded-2xl border border-slate-200 p-6 space-y-4">
        <div className="border-b border-slate-100 pb-3">
          <span className="text-xs font-mono uppercase tracking-wider text-slate-600">
            Formulation Architecture
          </span>
          <h3 className="text-lg font-bold text-slate-900">
            Functional Role Distribution
          </h3>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left">
            <thead>
              <tr className="border-b border-slate-200 font-mono text-slate-600 uppercase">
                <th className="py-2.5">Functional Role</th>
                <th className="py-2.5 text-center">{productA.name}</th>
                <th className="py-2.5 text-center">{productB.name}</th>
                <th className="py-2.5 text-right">Observation</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {allRoles.map(role => {
                const countA = productA.ingredients.filter(i => i.role === role).length;
                const countB = productB.ingredients.filter(i => i.role === role).length;

                return (
                  <tr key={role} className="hover:bg-slate-50/80">
                    <td className="py-3 font-semibold text-slate-800">{role}</td>
                    <td className="py-3 text-center font-mono font-medium">
                      {countA > 0 ? <span className="text-slate-900">{countA}</span> : <span className="text-slate-300">—</span>}
                    </td>
                    <td className="py-3 text-center font-mono font-medium">
                      {countB > 0 ? <span className="text-slate-900">{countB}</span> : <span className="text-slate-300">—</span>}
                    </td>
                    <td className="py-3 text-right text-slate-500">
                      {countA > 0 && countB > 0
                        ? 'Parallel mechanism in both matrices'
                        : countA > 0
                        ? `Exclusive to ${productA.name}`
                        : `Exclusive to ${productB.name}`}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* Evidence Availability Metric Comparison */}
      <section className="bg-slate-50 rounded-2xl border border-slate-200 p-6 space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-slate-200">
          <div>
            <span className="text-xs font-mono uppercase tracking-wider text-slate-600">
              Corroboration Index
            </span>
            <h3 className="text-base font-bold text-slate-900">
              Scientific Evidence Availability
            </h3>
          </div>
          <span className="text-xs font-mono text-slate-500">Peer-Reviewed & Monograph Citations</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
          <div className="bg-white p-4 rounded-xl border border-slate-200">
            <span className="font-bold text-slate-900 block text-sm">{productA.name}</span>
            <div className="mt-2 space-y-1 text-slate-600">
              <div className="flex justify-between">
                <span>Unique Citations:</span>
                <span className="font-mono font-bold text-slate-900">
                  {new Set(productA.ingredients.flatMap(i => i.evidenceIds)).size}
                </span>
              </div>
              <div className="flex justify-between">
                <span>Defined Molecular Entities:</span>
                <span className="font-mono font-bold text-slate-900">
                  {productA.ingredients.filter(i => i.chemicalEntityId).length} / {productA.ingredients.length}
                </span>
              </div>
            </div>
          </div>

          <div className="bg-white p-4 rounded-xl border border-slate-200">
            <span className="font-bold text-slate-900 block text-sm">{productB.name}</span>
            <div className="mt-2 space-y-1 text-slate-600">
              <div className="flex justify-between">
                <span>Unique Citations:</span>
                <span className="font-mono font-bold text-slate-900">
                  {new Set(productB.ingredients.flatMap(i => i.evidenceIds)).size}
                </span>
              </div>
              <div className="flex justify-between">
                <span>Defined Molecular Entities:</span>
                <span className="font-mono font-bold text-slate-900">
                  {productB.ingredients.filter(i => i.chemicalEntityId).length} / {productB.ingredients.length}
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};
