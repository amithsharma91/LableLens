import React, { useState } from 'react';
import { Header, NavTab } from './components/common/Header';
import { DemoDisclaimer } from './components/common/DemoDisclaimer';
import { HomeView } from './views/HomeView';
import { ScanView } from './views/ScanView';
import { ProductAnalysisView } from './views/ProductAnalysisView';
import { IngredientDetailView } from './views/IngredientDetailView';
import { CompareView } from './views/CompareView';
import { SearchView } from './views/SearchView';
import { LearnView } from './views/LearnView';
import { Product, IngredientObservation, ChemicalEntity } from './types';
import { DEMO_PRODUCTS } from './data/demoProducts';
import { DEMO_CHEMICAL_ENTITIES } from './data/chemicalEntities';

type ActiveView = 'home' | 'scan' | 'analysis' | 'ingredient-detail' | 'compare' | 'catalog' | 'learn';

export default function App() {
  const [currentView, setCurrentView] = useState<ActiveView>('home');
  const [activeNavTab, setActiveNavTab] = useState<NavTab>('home');

  // Currently selected product for Analysis
  const [currentProduct, setCurrentProduct] = useState<Product>(DEMO_PRODUCTS[0]);

  // Currently selected ingredient for IngredientDetail
  const [selectedIngredientObs, setSelectedIngredientObs] = useState<IngredientObservation | null>(null);
  const [selectedChemicalEntity, setSelectedChemicalEntity] = useState<ChemicalEntity | null>(null);

  // Compare products state
  const [compareProductA, setCompareProductA] = useState<Product>(DEMO_PRODUCTS[0]);
  const [compareProductB, setCompareProductB] = useState<Product>(DEMO_PRODUCTS[1]);

  // Tab navigation handler from Header or Mobile bar
  const handleNavTabChange = (tab: NavTab) => {
    setActiveNavTab(tab);
    if (tab === 'home') setCurrentView('home');
    else if (tab === 'scan') setCurrentView('scan');
    else if (tab === 'compare') setCurrentView('compare');
    else if (tab === 'catalog') setCurrentView('catalog');
    else if (tab === 'learn') setCurrentView('learn');
  };

  // Trigger scan with an optional preset
  const handleStartScan = (preset?: Product) => {
    if (preset) {
      setCurrentProduct(preset);
    }
    setActiveNavTab('scan');
    setCurrentView('scan');
  };

  // Direct inspect of a demo product from Home
  const handleSelectProduct = (product: Product) => {
    setCurrentProduct(product);
    setCurrentView('analysis');
  };

  // From ScanView after user reviews/edits OCR tokens and clicks "Analyze Ingredients"
  const handleAnalysisReady = (analyzedProduct: Product) => {
    setCurrentProduct(analyzedProduct);
    setCurrentView('analysis');
  };

  // From ProductAnalysisView when user clicks "Why is this here? & Evidence"
  const handleSelectIngredient = (obs: IngredientObservation, entity: ChemicalEntity | null) => {
    setSelectedIngredientObs(obs);
    setSelectedChemicalEntity(entity);
    setCurrentView('ingredient-detail');
  };

  // From Catalog / SearchView
  const handleSelectEntityFromSearch = (entity: ChemicalEntity, sampleObs?: IngredientObservation) => {
    setSelectedChemicalEntity(entity);
    if (sampleObs) {
      setSelectedIngredientObs(sampleObs);
    } else {
      // Find or build observation
      const syntheticObs: IngredientObservation = {
        id: `synth_${entity.id}`,
        rawText: entity.preferredName,
        normalizedText: entity.preferredName,
        matchStatus: 'Matched',
        chemicalEntityId: entity.id,
        role: entity.chemicalClass,
        confidence: 'High',
        confidenceScore: 99,
        evidenceIds: [],
        whyIsThisHere: {
          whatIsIt: `${entity.preferredName} (${entity.chemicalClass}).`,
          whyUsed: 'Catalog reference entity.',
          relevantChemistry: entity.descriptors.join('. ') + '.',
          evidenceSupport: 'Indexed in authoritative reference chemical library.',
          uncertainties: entity.limitations || 'Data reflects curated demonstration repository.'
        }
      };
      setSelectedIngredientObs(syntheticObs);
    }
    setCurrentView('ingredient-detail');
  };

  // From ProductAnalysisView -> Compare shortcut
  const handleCompareWith = (product: Product) => {
    setCompareProductA(product);
    // Pick another product for comparison
    const alternative = DEMO_PRODUCTS.find(p => p.id !== product.id && p.domain === product.domain) ||
      DEMO_PRODUCTS.find(p => p.id !== product.id) ||
      DEMO_PRODUCTS[1];
    setCompareProductB(alternative);
    setActiveNavTab('compare');
    setCurrentView('compare');
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col font-sans antialiased selection:bg-slate-200">
      {/* Demo Disclaimer Banner */}
      <DemoDisclaimer />

      {/* Top Navigation & Mobile Bar */}
      <Header currentTab={activeNavTab} onTabChange={handleNavTabChange} />

      {/* Main Viewport Container */}
      <main className="flex-1 pb-20 md:pb-12">
        {currentView === 'home' && (
          <HomeView
            onStartScan={handleStartScan}
            onSelectProduct={handleSelectProduct}
            onNavigate={handleNavTabChange}
          />
        )}

        {currentView === 'scan' && (
          <ScanView
            initialProduct={currentProduct}
            onAnalysisReady={handleAnalysisReady}
          />
        )}

        {currentView === 'analysis' && (
          <ProductAnalysisView
            product={currentProduct}
            onSelectIngredient={handleSelectIngredient}
            onBackToScan={() => setCurrentView('scan')}
            onCompareWith={handleCompareWith}
          />
        )}

        {currentView === 'ingredient-detail' && selectedIngredientObs && (
          <IngredientDetailView
            observation={selectedIngredientObs}
            entity={selectedChemicalEntity}
            onBack={() => setCurrentView('analysis')}
          />
        )}

        {currentView === 'compare' && (
          <CompareView
            initialProductA={compareProductA}
            initialProductB={compareProductB}
            onInspectIngredient={(obs, ent) => handleSelectIngredient(obs, ent)}
          />
        )}

        {currentView === 'catalog' && (
          <SearchView
            onSelectEntity={handleSelectEntityFromSearch}
          />
        )}

        {currentView === 'learn' && (
          <LearnView />
        )}
      </main>

      {/* Minimalist Scientific Footer adhering to anti-slop guidelines */}
      <footer className="border-t border-slate-200 bg-white py-6 px-4 text-xs text-slate-500">
        <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="font-mono font-bold text-slate-900">LabelLens</span>
            <span>·</span>
            <span>Phase 1 Computational Chemistry Prototype</span>
          </div>

          <div className="flex items-center gap-4 text-slate-500">
            <span>Authoritative Sources: EFSA · US FDA · Codex · CIR</span>
            <span className="hidden sm:inline">·</span>
            <span className="hidden sm:inline">Zero Good/Bad Ratings</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
