import React, { useState, useRef, useEffect } from 'react';
import {
  Camera,
  Upload,
  Edit3,
  Trash2,
  Plus,
  ArrowRight,
  AlertTriangle,
  FileText,
  ChevronDown,
  ChevronUp,
  Image as ImageIcon,
  AlertCircle,
  Loader2,
  Sparkles,
  Layers,
  Percent,
  Globe,
  ShieldCheck,
  Search,
  CheckCircle2,
} from 'lucide-react';
import { Product, IngredientNode, OcrResponse } from '../types';
import { performServerSideOcr } from '../services/labelExtractionService';
import { processIngredientsPipeline, flattenIngredientTree, resolveTreeWithWebResearch } from '../lib/pipeline';
import { serializeIngredientTree } from '../lib/parsing/ingredientParser';
import { researchIngredientWithFallback } from '../services/webResearchService';
import { DEMO_PRODUCTS } from '../data/demoProducts';
import { DEMO_PRODUCT_IMAGES } from '../data/demoLabelImages';

interface ScanViewProps {
  initialProduct?: Product;
  onAnalysisReady: (product: Product) => void;
}

type ScanStage = 'input' | 'processing' | 'review';

export const ScanView: React.FC<ScanViewProps> = ({ initialProduct, onAnalysisReady }) => {
  // Preset scenarios (Default to Peanut Butter Bar with nested syntax)
  const defaultScenario = initialProduct || DEMO_PRODUCTS[0];

  const [productName, setProductName] = useState(defaultScenario.name);
  const [productDomain, setProductDomain] = useState(defaultScenario.domain);

  // Real Image State
  const [selectedImage, setSelectedImage] = useState<string | null>(
    DEMO_PRODUCT_IMAGES[defaultScenario.id] || null
  );
  const [selectedImageMime, setSelectedImageMime] = useState<string>('image/jpeg');
  const [imageFileName, setImageFileName] = useState<string>('demo_peanut_butter_label.svg');
  const [isDemoFixtureImage, setIsDemoFixtureImage] = useState<boolean>(true);

  // Workflow Stages: 'input' | 'processing' | 'review'
  const [scanStage, setScanStage] = useState<ScanStage>('input');

  // Loading indicator states: 'Scanning label...' -> 'Reading visible text...' -> 'Extracting ingredient candidates...'
  const [loadingStepText, setLoadingStepText] = useState<string>('Scanning label...');

  // OCR Extraction Results
  const [rawOcrText, setRawOcrText] = useState<string>('');
  const [ocrWarnings, setOcrWarnings] = useState<string[]>([]);
  const [ocrConfidence, setOcrConfidence] = useState<string>('High');

  // Hierarchical parsed ingredients tree
  const [tree, setTree] = useState<IngredientNode[]>([]);
  const [hierarchyCounts, setHierarchyCounts] = useState<{
    topLevelCount: number;
    nestedCount: number;
    totalCount: number;
  }>({ topLevelCount: 0, nestedCount: 0, totalCount: 0 });

  // Review UI States
  const [activeEditingId, setActiveEditingId] = useState<string | null>(null);
  const [editTextValue, setEditTextValue] = useState<string>('');
  const [newIngredientInput, setNewIngredientInput] = useState<string>('');
  const [isAddingNew, setIsAddingNew] = useState<boolean>(false);
  const [addingSubIngredientParentId, setAddingSubIngredientParentId] = useState<string | null>(null);
  const [newSubIngredientInput, setNewSubIngredientInput] = useState<string>('');
  const [isRawTextExpanded, setIsRawTextExpanded] = useState<boolean>(false);
  const [expandedGroupIds, setExpandedGroupIds] = useState<Record<string, boolean>>({});

  // Web Research States (Phase 1.3)
  const [isResearchingWeb, setIsResearchingWeb] = useState<boolean>(false);
  const [researchProgressMsg, setResearchProgressMsg] = useState<string>('');
  const [researchingNodeId, setResearchingNodeId] = useState<string | null>(null);

  // Error State
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);

  // Manual fallback toggle
  const [showManualFallback, setShowManualFallback] = useState<boolean>(false);
  const [manualFallbackText, setManualFallbackText] = useState<string>('');

  // Refs for hidden inputs
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);

  // Loading animation stepper
  useEffect(() => {
    let timer1: any;
    let timer2: any;
    if (scanStage === 'processing') {
      setLoadingStepText('Scanning label...');
      timer1 = setTimeout(() => {
        setLoadingStepText('Reading visible text...');
      }, 900);
      timer2 = setTimeout(() => {
        setLoadingStepText('Extracting ingredient candidates...');
      }, 1900);
    }
    return () => {
      clearTimeout(timer1);
      clearTimeout(timer2);
    };
  }, [scanStage]);

  // Handle Preset selection
  const handleSelectPreset = (preset: Product) => {
    setProductName(preset.name);
    setProductDomain(preset.domain);
    setErrorMessage(null);
    setErrorCode(null);

    const demoImage = DEMO_PRODUCT_IMAGES[preset.id];
    if (demoImage) {
      setSelectedImage(demoImage);
      setSelectedImageMime('image/svg+xml');
      setImageFileName(`${preset.id}_demo_label.svg`);
      setIsDemoFixtureImage(true);
    } else {
      setSelectedImage(null);
      setIsDemoFixtureImage(false);
    }

    setScanStage('input');
    setTree([]);
    setRawOcrText('');
  };

  // Convert uploaded File to base64
  const handleFileSelected = (file: File) => {
    setErrorMessage(null);
    setErrorCode(null);

    if (file.size > 20 * 1024 * 1024) {
      setErrorMessage('Image file is too large (exceeds 20MB). Please select a compressed image.');
      setErrorCode('IMAGE_TOO_LARGE');
      return;
    }

    const allowed = ['image/jpeg', 'image/png', 'image/webp', 'image/heic', 'image/heif'];
    if (!allowed.includes(file.type.toLowerCase()) && !file.type.startsWith('image/')) {
      setErrorMessage(`Unsupported format (${file.type}). Please upload a JPEG, PNG, or WebP photo.`);
      setErrorCode('UNSUPPORTED_FORMAT');
      return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
      const result = e.target?.result as string;
      setSelectedImage(result);
      setSelectedImageMime(file.type || 'image/jpeg');
      setImageFileName(file.name);
      setIsDemoFixtureImage(false);
      setScanStage('input');
      setTree([]);
    };
    reader.onerror = () => {
      setErrorMessage('Failed to read image from device.');
      setErrorCode('FILE_READ_ERROR');
    };
    reader.readAsDataURL(file);
  };

  const handleDragOver = (e: React.DragEvent) => e.preventDefault();
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelected(e.dataTransfer.files[0]);
    }
  };

  const handleRemoveImage = () => {
    setSelectedImage(null);
    setImageFileName('');
    setIsDemoFixtureImage(false);
    setErrorMessage(null);
    setTree([]);
    setScanStage('input');
  };

  // Helper to convert SVG data URLs to PNG for Gemini OCR
  const rasterizeSvgToPng = (svgDataUrl: string): Promise<string> => {
    return new Promise((resolve) => {
      const img = new Image();
      img.crossOrigin = 'anonymous';
      img.onload = () => {
        const canvas = document.createElement('canvas');
        canvas.width = 800;
        canvas.height = 520;
        const ctx = canvas.getContext('2d');
        if (ctx) {
          ctx.fillStyle = '#ffffff';
          ctx.fillRect(0, 0, canvas.width, canvas.height);
          ctx.drawImage(img, 0, 0);
          resolve(canvas.toDataURL('image/png'));
        } else {
          resolve(svgDataUrl);
        }
      };
      img.onerror = () => resolve(svgDataUrl);
      img.src = svgDataUrl;
    });
  };

  // Helper to process raw text through the parentheses-aware pipeline
  const processRawTextToTree = (text: string, confidence: string = 'High') => {
    const pipeline = processIngredientsPipeline(text, productDomain, confidence);
    setTree(pipeline.tree);
    setHierarchyCounts(pipeline.counts);

    // Auto-expand all formulation groups with children
    const initialExpanded: Record<string, boolean> = {};
    for (const node of pipeline.tree) {
      if (node.children && node.children.length > 0) {
        initialExpanded[node.id] = true;
      }
    }
    setExpandedGroupIds(initialExpanded);
  };

  // Core Action: Perform Gemini Vision OCR
  const handleExtractTextWithGemini = async () => {
    if (!selectedImage) {
      setErrorMessage('No image selected. Please take a photo or select an image file.');
      setErrorCode('NO_IMAGE');
      return;
    }

    setScanStage('processing');
    setErrorMessage(null);
    setErrorCode(null);

    try {
      let imageToSend = selectedImage;
      let mimeToSend = selectedImageMime;

      if (selectedImage.startsWith('data:image/svg+xml')) {
        imageToSend = await rasterizeSvgToPng(selectedImage);
        mimeToSend = 'image/png';
      }

      const ocrResult: OcrResponse = await performServerSideOcr(imageToSend, mimeToSend);

      if (!ocrResult.raw_ocr_text || ocrResult.raw_ocr_text.trim().length === 0) {
        throw {
          message: 'Label text could not be reliably extracted. Please upload a clearer image or enter the text manually.',
          code: 'UNREADABLE_LABEL',
        };
      }

      const rawText = ocrResult.raw_ocr_text.trim();
      setRawOcrText(rawText);
      setOcrWarnings(ocrResult.warnings || []);
      setOcrConfidence(ocrResult.ocr_confidence || 'High');

      // Parentheses-aware structural parsing
      processRawTextToTree(rawText, ocrResult.ocr_confidence || 'High');
      setScanStage('review');
    } catch (err: any) {
      console.error('OCR Extraction error:', err);
      const msg =
        err?.code === 'UNREADABLE_LABEL'
          ? 'Label text could not be reliably extracted. Please upload a clearer image or enter the text manually.'
          : err?.message || 'OCR request failed. Please check the image and try again.';

      setErrorMessage(msg);
      setErrorCode(err?.code || 'OCR_FAILED');
      setScanStage('input');
    }
  };

  // Handle Manual Fallback Submission
  const handleProcessManualFallback = (e: React.FormEvent) => {
    e.preventDefault();
    if (!manualFallbackText.trim()) return;

    setRawOcrText(manualFallbackText.trim());
    setOcrWarnings(['Manual text entry fallback utilized.']);
    setOcrConfidence('Manual Entry');

    // Structural parsing
    processRawTextToTree(manualFallbackText.trim(), 'Manual Entry');
    setScanStage('review');
    setShowManualFallback(false);
  };

  // Toggle group expansion
  const toggleGroupExpand = (nodeId: string) => {
    setExpandedGroupIds((prev) => ({
      ...prev,
      [nodeId]: !prev[nodeId],
    }));
  };

  // Edit token handlers
  const handleStartEditing = (node: IngredientNode) => {
    setActiveEditingId(node.id);
    setEditTextValue(node.rawText);
  };

  const handleSaveEdit = (targetId: string) => {
    // Reconstruct raw text by updating the edited node and re-parsing
    function updateRawInTree(nodes: IngredientNode[]): boolean {
      for (const n of nodes) {
        if (n.id === targetId) {
          n.rawText = editTextValue.trim();
          n.name = editTextValue.trim();
          n.isCustomEdited = true;
          return true;
        }
        if (n.children && n.children.length > 0) {
          if (updateRawInTree(n.children)) return true;
        }
      }
      return false;
    }

    const updatedTree = [...tree];
    updateRawInTree(updatedTree);

    // Reconstruct hierarchical statement using serializeIngredientTree
    const reconstructed = serializeIngredientTree(updatedTree);
    setRawOcrText(reconstructed);
    processRawTextToTree(reconstructed, ocrConfidence);
    setActiveEditingId(null);
  };

  // Delete node (whether top-level or child)
  const handleDeleteNode = (targetId: string) => {
    function removeNode(nodes: IngredientNode[]): IngredientNode[] {
      return nodes
        .filter((n) => n.id !== targetId)
        .map((n) => ({
          ...n,
          children: n.children ? removeNode(n.children) : [],
        }));
    }

    const newTree = removeNode(tree);
    const reconstructed = serializeIngredientTree(newTree);
    setRawOcrText(reconstructed);
    processRawTextToTree(reconstructed, ocrConfidence);
  };

  // Move top-level node up/down
  const handleMoveTopLevel = (index: number, direction: 'up' | 'down') => {
    const newTree = [...tree];
    const targetIndex = direction === 'up' ? index - 1 : index + 1;
    if (targetIndex < 0 || targetIndex >= newTree.length) return;
    const temp = newTree[index];
    newTree[index] = newTree[targetIndex];
    newTree[targetIndex] = temp;

    const reconstructed = serializeIngredientTree(newTree);
    setRawOcrText(reconstructed);
    processRawTextToTree(reconstructed, ocrConfidence);
  };

  // Add top-level candidate manually
  const handleAddNewToken = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newIngredientInput.trim()) return;

    const added = newIngredientInput.trim();
    const updatedText = rawOcrText ? `${rawOcrText}, ${added}` : added;
    setRawOcrText(updatedText);
    processRawTextToTree(updatedText, ocrConfidence);
    setNewIngredientInput('');
    setIsAddingNew(false);
  };

  // Add sub-ingredient to a parent component
  const handleAddSubIngredient = (parentId: string) => {
    if (!newSubIngredientInput.trim()) return;
    const subText = newSubIngredientInput.trim();

    function addSubToNode(nodes: IngredientNode[]): boolean {
      for (const n of nodes) {
        if (n.id === parentId) {
          const fakeChild: any = {
            id: `temp_${Date.now()}`,
            name: subText,
            rawText: subText,
            children: [],
          };
          n.children = [...(n.children || []), fakeChild];
          return true;
        }
        if (n.children && n.children.length > 0) {
          if (addSubToNode(n.children)) return true;
        }
      }
      return false;
    }

    const updatedTree = [...tree];
    addSubToNode(updatedTree);
    const reconstructed = serializeIngredientTree(updatedTree);
    setRawOcrText(reconstructed);
    processRawTextToTree(reconstructed, ocrConfidence);
    setNewSubIngredientInput('');
    setAddingSubIngredientParentId(null);
  };

  // Web Research Trigger for single node
  const handleResearchSingleNode = async (targetNode: IngredientNode) => {
    setResearchingNodeId(targetNode.id);
    try {
      const outcome = await researchIngredientWithFallback({
        ingredientName: targetNode.name,
        rawText: targetNode.rawText,
        identifier: targetNode.identifier,
        domain: productDomain,
        forceRefresh: true,
      });

      function updateNodeInTree(nodes: IngredientNode[]): IngredientNode[] {
        return nodes.map((n) => {
          if (n.id === targetNode.id) {
            if (outcome.webResearch) {
              return {
                ...n,
                webResearch: outcome.webResearch,
                verificationStatus: outcome.verificationStatus,
                role: outcome.webResearch.functionalRole || n.role,
                classification: outcome.webResearch.entityType,
                confidence: outcome.webResearch.confidenceLevel,
                confidenceScore: outcome.webResearch.confidenceScore,
                whyIsThisHere: {
                  whatIsIt: outcome.webResearch.summary,
                  whyUsed: outcome.webResearch.whyUsed,
                  relevantChemistry: outcome.webResearch.relevantChemistry,
                  evidenceSupport: outcome.webResearch.evidenceSupport,
                  uncertainties: outcome.webResearch.uncertainties,
                },
              };
            } else if (outcome.error) {
              return {
                ...n,
                verificationStatus: 'UNRESOLVED_UNKNOWN',
                researchError: outcome.error,
              };
            }
          }
          if (n.children && n.children.length > 0) {
            return {
              ...n,
              children: updateNodeInTree(n.children),
            };
          }
          return n;
        });
      }

      setTree(updateNodeInTree(tree));
    } catch (err) {
      console.error('Single node research error:', err);
    } finally {
      setResearchingNodeId(null);
    }
  };

  // Batch research all unverified candidates
  const handleResearchAllCandidates = async () => {
    setIsResearchingWeb(true);
    setResearchProgressMsg('Starting Google Search Grounding for uncataloged ingredients...');
    try {
      const updated = await resolveTreeWithWebResearch(tree, productDomain, (msg) => {
        setResearchProgressMsg(msg);
      });
      setTree(updated);
    } catch (err) {
      console.error('Batch research failed:', err);
    } finally {
      setIsResearchingWeb(false);
      setResearchProgressMsg('');
    }
  };

  // Final Action: Send to Product Analysis with automatic Web-Grounding for unresolved candidates
  const handleProceedToAnalysis = async () => {
    function checkNeedsResearch(nodes: IngredientNode[]): boolean {
      for (const n of nodes) {
        if (n.verificationStatus !== 'LOCAL_VERIFIED' && !n.webResearch) {
          return true;
        }
        if (n.children && checkNeedsResearch(n.children)) return true;
      }
      return false;
    }

    let finalTree = tree;
    if (checkNeedsResearch(tree)) {
      setIsResearchingWeb(true);
      setResearchProgressMsg('Grounding ingredients against authoritative regulatory sources...');
      try {
        finalTree = await resolveTreeWithWebResearch(tree, productDomain, (msg) => {
          setResearchProgressMsg(msg);
        });
        setTree(finalTree);
      } catch (err) {
        console.error('Web research during analysis transition failed:', err);
      } finally {
        setIsResearchingWeb(false);
        setResearchProgressMsg('');
      }
    }

    const observations = flattenIngredientTree(finalTree);
    const analyzedProduct: Product = {
      id: `prod_${Date.now()}`,
      name: productName || 'Scanned Label Formulation',
      brand: 'Packaging Sample',
      domain: productDomain,
      labelText: rawOcrText,
      ingredientsTree: finalTree,
      ingredients: observations,
      imageUrl: selectedImage || undefined,
    };
    onAnalysisReady(analyzedProduct);
  };

  return (
    <div className="max-w-4xl mx-auto px-4 py-6 space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2 text-xs font-mono text-slate-500 mb-1">
          <span>PIPELINE PHASE 1.2</span>
          <span>·</span>
          <span>STRUCTURAL HIERARCHICAL PARSING</span>
        </div>
        <h1 className="text-2xl sm:text-3xl font-bold text-slate-900">
          Scan & Extract Label
        </h1>
        <p className="text-sm text-slate-600 mt-1 max-w-2xl leading-relaxed">
          Upload an authentic label image. The parentheses-aware pipeline preserves formulation hierarchies,
          extracts sub-ingredients, and isolates additive codes before chemical analysis.
        </p>
      </div>

      {/* Preset Buttons */}
      <div className="bg-slate-100/90 p-3.5 rounded-xl border border-slate-200">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 mb-2">
          <span className="text-xs font-mono font-semibold text-slate-700 uppercase">
            Curated Demonstration Labels
          </span>
          <span className="text-[11px] text-slate-500">
            Includes nested packaging statements & typo cases
          </span>
        </div>
        <div className="flex flex-wrap gap-2">
          {DEMO_PRODUCTS.map((p) => {
            const isPeanutBar = p.id === 'prod_peanut_butter_bar';
            const isTypoSample = p.id === 'prod_cocoa_spread';
            const isActive = productName === p.name;
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => handleSelectPreset(p)}
                className={`text-xs px-3 py-1.5 rounded-lg border transition-all cursor-pointer text-left ${
                  isActive
                    ? 'bg-slate-900 text-white border-slate-900 shadow-xs'
                    : 'bg-white text-slate-700 border-slate-200 hover:border-slate-400'
                }`}
              >
                <span className="font-medium">{p.name}</span>
                {isPeanutBar && (
                  <span
                    className={`ml-1.5 text-[10px] px-1 py-0.2 rounded font-mono ${
                      isActive ? 'bg-blue-400 text-slate-950 font-bold' : 'bg-blue-100 text-blue-800'
                    }`}
                  >
                    nested syntax
                  </span>
                )}
                {isTypoSample && (
                  <span
                    className={`ml-1.5 text-[10px] px-1 py-0.2 rounded font-mono ${
                      isActive ? 'bg-amber-400 text-slate-950 font-bold' : 'bg-amber-100 text-amber-800'
                    }`}
                  >
                    typo demo
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Error Callout */}
      {errorMessage && (
        <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-xs text-rose-900 flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <h4 className="font-bold">Extraction Error</h4>
            <p className="leading-relaxed">{errorMessage}</p>
            <div className="pt-2 flex items-center gap-3">
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="font-semibold underline hover:text-rose-950 cursor-pointer"
              >
                Upload different image
              </button>
              <span>·</span>
              <button
                type="button"
                onClick={() => setShowManualFallback(true)}
                className="font-semibold underline hover:text-rose-950 cursor-pointer"
              >
                Enter text manually
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Product Metadata Inputs */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className="block text-[11px] font-mono text-slate-500 uppercase mb-1">
            Product Label Name
          </label>
          <input
            type="text"
            value={productName}
            onChange={(e) => setProductName(e.target.value)}
            className="w-full text-xs sm:text-sm px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-900"
            placeholder="e.g. Peanut Butter & Dark Chocolate Protein Slab"
          />
        </div>

        <div>
          <label className="block text-[11px] font-mono text-slate-500 uppercase mb-1">
            Category / Domain
          </label>
          <select
            value={productDomain}
            onChange={(e) => setProductDomain(e.target.value as any)}
            className="w-full text-xs sm:text-sm px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-900"
          >
            <option value="Food">Food</option>
            <option value="Beverage">Beverage</option>
            <option value="Cosmetics">Cosmetics</option>
            <option value="Personal Care">Personal Care</option>
          </select>
        </div>
      </div>

      {/* Main Image Input & Preview Stage */}
      <div className="bg-white border border-slate-200 rounded-2xl p-5 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-slate-100">
          <div>
            <h2 className="text-base font-bold text-slate-900">
              Product Label Image
            </h2>
            <p className="text-xs text-slate-500">
              {isDemoFixtureImage
                ? 'Curated demonstration label loaded and ready for vision OCR.'
                : selectedImage
                ? `Uploaded file: ${imageFileName}`
                : 'Take a clear photograph of the ingredient statement on packaging.'}
            </p>
          </div>

          <input
            type="file"
            ref={fileInputRef}
            onChange={(e) => e.target.files?.[0] && handleFileSelected(e.target.files[0])}
            accept="image/*"
            className="hidden"
          />
          <input
            type="file"
            ref={cameraInputRef}
            onChange={(e) => e.target.files?.[0] && handleFileSelected(e.target.files[0])}
            accept="image/*"
            capture="environment"
            className="hidden"
          />

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => cameraInputRef.current?.click()}
              className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer min-h-[38px]"
              title="Open camera"
            >
              <Camera className="w-3.5 h-3.5" />
              <span>Camera</span>
            </button>

            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer min-h-[38px]"
              title="Upload file"
            >
              <Upload className="w-3.5 h-3.5" />
              <span>Upload Image</span>
            </button>

            {selectedImage && (
              <button
                type="button"
                onClick={handleRemoveImage}
                className="px-2.5 py-1.5 text-xs text-rose-600 hover:bg-rose-50 rounded-lg transition-colors cursor-pointer"
              >
                Clear
              </button>
            )}
          </div>
        </div>

        {/* Viewfinder Preview */}
        {selectedImage ? (
          <div className="relative border border-slate-200 rounded-xl overflow-hidden bg-slate-950 flex flex-col items-center justify-center p-2 sm:p-4 min-h-[260px] max-h-[460px]">
            <img
              src={selectedImage}
              alt="Label packaging preview"
              className="w-auto h-auto max-h-[420px] max-w-full object-contain rounded select-none"
            />

            {scanStage === 'processing' && (
              <div className="absolute inset-0 bg-slate-950/65 backdrop-blur-xs flex flex-col items-center justify-center text-white p-4 space-y-3">
                <Loader2 className="w-8 h-8 animate-spin text-blue-400" />
                <div className="text-center space-y-1">
                  <p className="text-sm font-semibold tracking-wide">{loadingStepText}</p>
                  <p className="text-xs text-slate-400 font-mono">
                    Verbatim optical parsing · No chemical inference
                  </p>
                </div>
                <div className="w-48 h-1 bg-slate-800 rounded-full overflow-hidden">
                  <div className="w-full h-full bg-blue-500 animate-pulse" />
                </div>
              </div>
            )}
          </div>
        ) : (
          <div
            onDragOver={handleDragOver}
            onDrop={handleDrop}
            className="border-2 border-dashed border-slate-300 rounded-xl p-8 text-center bg-slate-50/50 hover:bg-slate-50 transition-colors flex flex-col items-center justify-center min-h-[220px] space-y-3"
          >
            <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center text-slate-600">
              <ImageIcon className="w-6 h-6" />
            </div>
            <div>
              <p className="text-sm font-semibold text-slate-900">
                Drag and drop label photo here
              </p>
              <p className="text-xs text-slate-500 mt-0.5">
                or tap Camera on mobile to take a direct photo
              </p>
            </div>
            <div className="flex items-center gap-2 pt-1">
              <button
                type="button"
                onClick={() => cameraInputRef.current?.click()}
                className="px-4 py-2 bg-slate-900 text-white rounded-lg text-xs font-semibold cursor-pointer shadow-xs"
              >
                Snap with Camera
              </button>
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="px-3.5 py-2 bg-white border border-slate-300 text-slate-700 rounded-lg text-xs font-semibold cursor-pointer hover:bg-slate-100"
              >
                Choose Photo
              </button>
            </div>
          </div>
        )}

        {/* Action Row */}
        <div className="pt-2 flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="text-[11px] text-slate-500 max-w-sm">
            <span className="font-semibold text-slate-700">Privacy Notice:</span> Your image is processed by the LabelLens OCR service to extract visible label text. No chemical identification is performed during OCR.
          </div>

          <button
            type="button"
            disabled={!selectedImage || scanStage === 'processing'}
            onClick={handleExtractTextWithGemini}
            className="w-full sm:w-auto px-6 py-3 bg-slate-900 hover:bg-slate-800 disabled:opacity-40 text-white rounded-xl text-xs sm:text-sm font-semibold flex items-center justify-center gap-2 shadow-sm transition-all cursor-pointer min-h-[44px]"
          >
            {scanStage === 'processing' ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Reading Label...</span>
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4 text-blue-400" />
                <span>Extract Ingredients (Gemini OCR)</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Manual Fallback Input */}
      <div className="border border-slate-200 rounded-xl bg-white overflow-hidden">
        <button
          type="button"
          onClick={() => setShowManualFallback(!showManualFallback)}
          className="w-full px-4 py-3 text-left flex items-center justify-between text-xs font-medium text-slate-600 hover:bg-slate-50 cursor-pointer"
        >
          <span>Enter label text manually (Fallback)</span>
          {showManualFallback ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>

        {showManualFallback && (
          <form onSubmit={handleProcessManualFallback} className="p-4 border-t border-slate-100 bg-slate-50 space-y-3">
            <p className="text-xs text-slate-500">
              Paste the verbatim ingredient statement including nested parentheses:
            </p>
            <textarea
              rows={3}
              value={manualFallbackText}
              onChange={(e) => setManualFallbackText(e.target.value)}
              placeholder="e.g. Peanut Butter (83%) (Peanut (68%), Jaggery Powder (14%), Stabilizer (INS471), Salt), Whey Protein Concentrate (10%), Dark Chocolate (7%) (Cocoa Powder, Cocoa Butter, Natural Flavouring)"
              className="w-full text-xs font-mono p-3 bg-white border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-900"
            />
            <button
              type="submit"
              disabled={!manualFallbackText.trim()}
              className="px-4 py-2 bg-slate-900 text-white text-xs font-semibold rounded-lg disabled:opacity-40 cursor-pointer"
            >
              Parse Hierarchical Statement
            </button>
          </form>
        )}
      </div>

      {/* OCR RESULT — REVIEW REQUIRED (Hierarchical UI) */}
      {scanStage === 'review' && tree.length > 0 && (
        <section className="bg-white border-2 border-slate-900/10 rounded-2xl p-5 sm:p-6 space-y-5 shadow-xs">
          {/* Review Header Banner */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-4 border-b border-slate-200">
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="px-2.5 py-0.5 text-xs font-mono font-bold bg-amber-100 text-amber-950 rounded-md border border-amber-300">
                  OCR RESULT — REVIEW REQUIRED
                </span>
                <span className="text-xs font-mono text-slate-600">
                  {hierarchyCounts.topLevelCount} primary component{hierarchyCounts.topLevelCount !== 1 ? 's' : ''}
                  {hierarchyCounts.nestedCount > 0 ? ` · ${hierarchyCounts.nestedCount} nested sub-ingredient${hierarchyCounts.nestedCount !== 1 ? 's' : ''}` : ''}
                </span>
              </div>
              <p className="text-xs text-slate-600 mt-1">
                Parentheses-aware parsing preserved hierarchy. Review top-level components and nested sub-ingredients before chemical analysis.
              </p>
            </div>

            <div className="flex items-center gap-2 self-start sm:self-auto flex-wrap">
              <button
                type="button"
                onClick={handleResearchAllCandidates}
                disabled={isResearchingWeb}
                className="px-3 py-1.5 text-xs font-semibold text-indigo-700 bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 rounded-lg flex items-center gap-1.5 transition-colors cursor-pointer min-h-[38px]"
                title="Ground uncataloged ingredients via Google Search before final analysis"
              >
                {isResearchingWeb ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-600" />
                ) : (
                  <Globe className="w-3.5 h-3.5 text-indigo-600" />
                )}
                <span>Research All Candidates</span>
              </button>

              <button
                type="button"
                onClick={() => setIsAddingNew(true)}
                className="px-3 py-1.5 text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg flex items-center gap-1.5 transition-colors self-start sm:self-auto cursor-pointer min-h-[38px]"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Add Candidate</span>
              </button>
            </div>
          </div>

          {/* Web Research Live Banner (Phase 1.3) */}
          {isResearchingWeb && (
            <div className="p-3.5 bg-indigo-50 border border-indigo-200 rounded-xl flex items-center gap-3 text-xs text-indigo-950 animate-pulse">
              <Loader2 className="w-4 h-4 text-indigo-600 animate-spin shrink-0" />
              <div>
                <strong className="font-semibold block">Google Search Grounding & Regulatory Research Active</strong>
                <p className="text-indigo-800 text-[11px] mt-0.5">
                  {researchProgressMsg || 'Querying regulatory authorities (EFSA, US FDA, Codex Alimentarius) and extracting candidate facts...'}
                </p>
              </div>
            </div>
          )}

          {/* Collapsible: Raw OCR Text (Provenance & Debugging) */}
          <div className="bg-slate-50 border border-slate-200 rounded-xl overflow-hidden">
            <button
              type="button"
              onClick={() => setIsRawTextExpanded(!isRawTextExpanded)}
              className="w-full px-4 py-2.5 flex items-center justify-between text-xs font-mono font-semibold text-slate-700 hover:bg-slate-100 cursor-pointer"
            >
              <div className="flex items-center gap-2">
                <FileText className="w-3.5 h-3.5 text-slate-500" />
                <span>View raw OCR text (Provenance & Debugging)</span>
              </div>
              {isRawTextExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>

            {isRawTextExpanded && (
              <div className="p-4 border-t border-slate-200 bg-white font-mono text-xs text-slate-800 leading-relaxed whitespace-pre-wrap">
                {rawOcrText || 'No raw text string.'}
                {ocrWarnings.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-slate-100 text-[11px] text-amber-800 space-y-1">
                    <span className="font-bold uppercase tracking-wider block">OCR Observations:</span>
                    {ocrWarnings.map((w, idx) => (
                      <p key={idx}>· {w}</p>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Add candidate input */}
          {isAddingNew && (
            <form
              onSubmit={handleAddNewToken}
              className="p-3 bg-blue-50/50 border border-blue-200 rounded-xl flex items-center gap-2"
            >
              <input
                type="text"
                value={newIngredientInput}
                onChange={(e) => setNewIngredientInput(e.target.value)}
                placeholder="Type top-level ingredient candidate..."
                className="flex-1 text-xs px-3 py-2 bg-white border border-blue-300 rounded-lg focus:outline-none"
                autoFocus
              />
              <button
                type="submit"
                className="px-3 py-2 bg-slate-900 text-white rounded-lg text-xs font-semibold cursor-pointer"
              >
                Add
              </button>
              <button
                type="button"
                onClick={() => setIsAddingNew(false)}
                className="px-2 py-2 text-xs text-slate-500 hover:text-slate-700 cursor-pointer"
              >
                Cancel
              </button>
            </form>
          )}

          {/* Hierarchical Ingredient Cards List */}
          <div className="space-y-3">
            {tree.map((node, index) => {
              const isEditing = activeEditingId === node.id;
              const hasChildren = node.children && node.children.length > 0;
              const isExpanded = expandedGroupIds[node.id] ?? true;
              const hasTypo = node.classification === 'OCR_UNCERTAIN' || node.name.toLowerCase().includes('emulsifer');

              return (
                <div
                  key={node.id}
                  className={`rounded-xl border transition-all ${
                    hasTypo
                      ? 'bg-amber-50/70 border-amber-300'
                      : hasChildren
                      ? 'bg-slate-50/70 border-slate-300'
                      : 'bg-white border-slate-200'
                  }`}
                >
                  {/* Top-Level Component Header */}
                  <div className="p-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div className="flex items-start sm:items-center gap-3 flex-1 min-w-0">
                      <span className="font-mono text-xs text-slate-500 w-5 shrink-0 text-center font-bold">
                        {index + 1}.
                      </span>

                      {isEditing ? (
                        <div className="flex-1 flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
                          <input
                            type="text"
                            value={editTextValue}
                            onChange={(e) => setEditTextValue(e.target.value)}
                            className="flex-1 text-xs font-semibold px-3 py-2 bg-white border-2 border-blue-500 rounded-md focus:outline-none"
                            autoFocus
                          />
                          <div className="flex items-center gap-1.5 self-end sm:self-auto">
                            <button
                              type="button"
                              onClick={() => handleSaveEdit(node.id)}
                              className="px-3 py-2 bg-slate-900 text-white text-xs font-semibold rounded-md cursor-pointer"
                            >
                              Save
                            </button>
                            <button
                              type="button"
                              onClick={() => setActiveEditingId(null)}
                              className="px-2 py-2 text-slate-500 text-xs hover:text-slate-800 cursor-pointer"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-sm font-bold text-slate-900">
                              {node.name}
                            </span>

                            {node.percentage !== null && (
                              <span className="text-[11px] font-mono px-2 py-0.5 bg-blue-50 text-blue-800 rounded font-semibold border border-blue-200">
                                {node.percentage}%
                              </span>
                            )}

                            {node.identifier && (
                              <span className="text-[11px] font-mono px-2 py-0.5 bg-indigo-50 text-indigo-800 rounded font-semibold border border-indigo-200">
                                {node.identifier}
                              </span>
                            )}

                            <span className="text-[10px] font-mono px-1.5 py-0.5 bg-slate-100 text-slate-700 rounded border border-slate-200">
                              {node.classification.replace(/_/g, ' ')}
                            </span>

                            {/* Verification Status Badges (Phase 1.3) */}
                            {node.verificationStatus === 'LOCAL_VERIFIED' && (
                              <span className="text-[10px] font-mono px-1.5 py-0.5 bg-emerald-50 text-emerald-800 rounded font-semibold border border-emerald-200 inline-flex items-center gap-1">
                                <ShieldCheck className="w-3 h-3 text-emerald-600" />
                                <span>Local Catalog</span>
                              </span>
                            )}
                            {node.verificationStatus === 'VERIFIED_WEB_BACKED' && (
                              <span className="text-[10px] font-mono px-1.5 py-0.5 bg-indigo-50 text-indigo-800 rounded font-semibold border border-indigo-200 inline-flex items-center gap-1">
                                <Globe className="w-3 h-3 text-indigo-600" />
                                <span>Verified Web-Backed</span>
                              </span>
                            )}
                            {node.verificationStatus === 'WEB_RESEARCHED_CANDIDATE' && (
                              <span className="text-[10px] font-mono px-1.5 py-0.5 bg-sky-50 text-sky-800 rounded font-semibold border border-sky-200 inline-flex items-center gap-1">
                                <Search className="w-3 h-3 text-sky-600" />
                                <span>Web Candidate</span>
                              </span>
                            )}
                            {node.verificationStatus === 'UNRESOLVED_UNKNOWN' && (
                              <span className="text-[10px] font-mono px-1.5 py-0.5 bg-amber-50 text-amber-800 rounded font-semibold border border-amber-200 inline-flex items-center gap-1">
                                <AlertCircle className="w-3 h-3 text-amber-600" />
                                <span>{node.webResearch ? 'Unresolved Umbrella' : 'Web Research Required'}</span>
                              </span>
                            )}

                            {/* Quick single-item research button if uncataloged */}
                            {node.verificationStatus !== 'LOCAL_VERIFIED' && !node.webResearch && (
                              <button
                                type="button"
                                onClick={() => handleResearchSingleNode(node)}
                                disabled={researchingNodeId === node.id}
                                className="text-[10px] font-semibold text-blue-700 hover:text-blue-900 border border-blue-200 bg-blue-50/70 hover:bg-blue-100 rounded px-2 py-0.5 inline-flex items-center gap-1 cursor-pointer transition-colors"
                                title="Ground this ingredient with Google Search"
                              >
                                {researchingNodeId === node.id ? (
                                  <Loader2 className="w-3 h-3 animate-spin text-blue-600" />
                                ) : (
                                  <Globe className="w-3 h-3 text-blue-600" />
                                )}
                                <span>Research Web</span>
                              </button>
                            )}
                          </div>

                          {/* Typo Warning */}
                          {hasTypo && (
                            <div className="mt-1 flex items-center gap-1.5 text-xs text-amber-900 font-medium">
                              <AlertTriangle className="w-3.5 h-3.5 text-amber-700 shrink-0" />
                              <span>Possible OCR issue:</span>
                              <span className="font-mono underline font-bold">"{node.rawText}"</span>
                              <span className="text-slate-600 ml-1">
                                (Tap Edit to correct to Emulsifier)
                              </span>
                            </div>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Actions: Reorder, Edit, Delete */}
                    {!isEditing && (
                      <div className="flex items-center gap-1.5 self-end sm:self-auto shrink-0">
                        {/* Top-Level Reorder */}
                        <div className="flex items-center border border-slate-200 rounded-md bg-white overflow-hidden shadow-2xs">
                          <button
                            type="button"
                            disabled={index === 0}
                            onClick={() => handleMoveTopLevel(index, 'up')}
                            className="px-2 py-1.5 text-xs text-slate-600 hover:bg-slate-100 disabled:opacity-25 cursor-pointer min-w-[28px]"
                            title="Move up"
                          >
                            ▲
                          </button>
                          <button
                            type="button"
                            disabled={index === tree.length - 1}
                            onClick={() => handleMoveTopLevel(index, 'down')}
                            className="px-2 py-1.5 text-xs text-slate-600 hover:bg-slate-100 disabled:opacity-25 cursor-pointer border-l border-slate-200 min-w-[28px]"
                            title="Move down"
                          >
                            ▼
                          </button>
                        </div>

                        <button
                          type="button"
                          onClick={() => handleStartEditing(node)}
                          className="px-2.5 py-1.5 bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 rounded-md text-xs font-medium flex items-center gap-1 cursor-pointer transition-colors shadow-2xs min-h-[32px]"
                        >
                          <Edit3 className="w-3.5 h-3.5 text-slate-500" />
                          <span>Edit</span>
                        </button>

                        <button
                          type="button"
                          onClick={() => handleDeleteNode(node.id)}
                          className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-md transition-colors cursor-pointer min-h-[32px] min-w-[32px] flex items-center justify-center"
                          title="Delete"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    )}
                  </div>

                  {/* Expandable Sub-Ingredients Accordion (Formulation Group UI) */}
                  {hasChildren && (
                    <div className="border-t border-slate-200 bg-white/80 rounded-b-xl overflow-hidden">
                      <button
                        type="button"
                        onClick={() => toggleGroupExpand(node.id)}
                        className="w-full px-4 py-2 flex items-center justify-between text-xs font-mono font-semibold text-slate-700 hover:bg-slate-100/80 cursor-pointer bg-slate-100/50"
                      >
                        <div className="flex items-center gap-2">
                          <Layers className="w-3.5 h-3.5 text-blue-600" />
                          <span>
                            {isExpanded ? '▼' : '▶'} Contains {node.children.length} declared sub-ingredient{node.children.length !== 1 ? 's' : ''}:
                          </span>
                        </div>
                        <span className="text-[11px] text-slate-500 font-normal">
                          {isExpanded ? 'Hide' : 'Expand'} sub-components
                        </span>
                      </button>

                      {isExpanded && (
                        <div className="p-3 space-y-2 pl-6 sm:pl-10 divide-y divide-slate-100">
                          {node.children.map((child, cIdx) => {
                            const isChildEditing = activeEditingId === child.id;
                            return (
                              <div
                                key={child.id}
                                className="pt-2 first:pt-0 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs"
                              >
                                {isChildEditing ? (
                                  <div className="flex-1 flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
                                    <input
                                      type="text"
                                      value={editTextValue}
                                      onChange={(e) => setEditTextValue(e.target.value)}
                                      className="flex-1 text-xs font-semibold px-2.5 py-1.5 bg-white border-2 border-blue-500 rounded-md focus:outline-none"
                                      autoFocus
                                    />
                                    <div className="flex items-center gap-1.5 self-end sm:self-auto">
                                      <button
                                        type="button"
                                        onClick={() => handleSaveEdit(child.id)}
                                        className="px-2.5 py-1.5 bg-slate-900 text-white rounded text-xs font-semibold cursor-pointer"
                                      >
                                        Save
                                      </button>
                                      <button
                                        type="button"
                                        onClick={() => setActiveEditingId(null)}
                                        className="px-2 py-1.5 text-xs text-slate-500 hover:text-slate-800 cursor-pointer"
                                      >
                                        Cancel
                                      </button>
                                    </div>
                                  </div>
                                ) : (
                                  <>
                                    <div className="flex items-center gap-2 flex-wrap">
                                      <span className="font-mono text-slate-400 text-[11px]">
                                        {index + 1}.{cIdx + 1}
                                      </span>
                                      <span className="font-semibold text-slate-900">
                                        {child.name}
                                      </span>
                                      {child.percentage !== null && (
                                        <span className="font-mono text-[10px] px-1.5 py-0.2 bg-blue-50 text-blue-800 rounded border border-blue-200">
                                          {child.percentage}%
                                        </span>
                                      )}
                                      {child.identifier && (
                                        <span className="font-mono text-[10px] px-1.5 py-0.2 bg-indigo-50 text-indigo-800 rounded border border-indigo-200">
                                          {child.identifier}
                                        </span>
                                      )}
                                      <span className="text-[10px] font-mono text-slate-500">
                                        · {child.classification.replace(/_/g, ' ')}
                                      </span>

                                      {/* Verification Status Badges for Child Nodes */}
                                      {child.verificationStatus === 'LOCAL_VERIFIED' && (
                                        <span className="text-[9px] font-mono px-1 py-0.2 bg-emerald-50 text-emerald-800 rounded font-semibold border border-emerald-200 inline-flex items-center gap-0.5">
                                          <ShieldCheck className="w-2.5 h-2.5 text-emerald-600" />
                                          <span>Local Catalog</span>
                                        </span>
                                      )}
                                      {child.verificationStatus === 'VERIFIED_WEB_BACKED' && (
                                        <span className="text-[9px] font-mono px-1 py-0.2 bg-indigo-50 text-indigo-800 rounded font-semibold border border-indigo-200 inline-flex items-center gap-0.5">
                                          <Globe className="w-2.5 h-2.5 text-indigo-600" />
                                          <span>Verified Web-Backed</span>
                                        </span>
                                      )}
                                      {child.verificationStatus === 'WEB_RESEARCHED_CANDIDATE' && (
                                        <span className="text-[9px] font-mono px-1 py-0.2 bg-sky-50 text-sky-800 rounded font-semibold border border-sky-200 inline-flex items-center gap-0.5">
                                          <Search className="w-2.5 h-2.5 text-sky-600" />
                                          <span>Web Candidate</span>
                                        </span>
                                      )}
                                      {child.verificationStatus === 'UNRESOLVED_UNKNOWN' && (
                                        <span className="text-[9px] font-mono px-1 py-0.2 bg-amber-50 text-amber-800 rounded font-semibold border border-amber-200 inline-flex items-center gap-0.5">
                                          <AlertCircle className="w-2.5 h-2.5 text-amber-600" />
                                          <span>{child.webResearch ? 'Unresolved Umbrella' : 'Web Research Required'}</span>
                                        </span>
                                      )}

                                      {/* Inline research for child node */}
                                      {child.verificationStatus !== 'LOCAL_VERIFIED' && !child.webResearch && (
                                        <button
                                          type="button"
                                          onClick={() => handleResearchSingleNode(child)}
                                          disabled={researchingNodeId === child.id}
                                          className="text-[9px] font-semibold text-blue-700 hover:text-blue-900 border border-blue-200 bg-blue-50/70 hover:bg-blue-100 rounded px-1.5 py-0.2 inline-flex items-center gap-0.5 cursor-pointer transition-colors"
                                          title="Ground this sub-ingredient with Google Search"
                                        >
                                          {researchingNodeId === child.id ? (
                                            <Loader2 className="w-2.5 h-2.5 animate-spin text-blue-600" />
                                          ) : (
                                            <Globe className="w-2.5 h-2.5 text-blue-600" />
                                          )}
                                          <span>Research</span>
                                        </button>
                                      )}
                                    </div>

                                    <div className="flex items-center gap-1 self-end sm:self-auto shrink-0">
                                      <button
                                        type="button"
                                        onClick={() => handleStartEditing(child)}
                                        className="p-1 text-slate-400 hover:text-slate-700 cursor-pointer"
                                        title="Edit sub-ingredient"
                                      >
                                        <Edit3 className="w-3 h-3" />
                                      </button>
                                      <button
                                        type="button"
                                        onClick={() => handleDeleteNode(child.id)}
                                        className="p-1 text-slate-400 hover:text-rose-600 cursor-pointer"
                                        title="Delete sub-ingredient"
                                      >
                                        <Trash2 className="w-3 h-3" />
                                      </button>
                                    </div>
                                  </>
                                )}
                              </div>
                            );
                          })}

                          {/* Add sub-ingredient inline form */}
                          <div className="pt-2">
                            {addingSubIngredientParentId === node.id ? (
                              <form
                                onSubmit={(e) => {
                                  e.preventDefault();
                                  handleAddSubIngredient(node.id);
                                }}
                                className="flex items-center gap-2"
                              >
                                <input
                                  type="text"
                                  value={newSubIngredientInput}
                                  onChange={(e) => setNewSubIngredientInput(e.target.value)}
                                  placeholder="e.g. Vanilla Extract or Salt (0.5%)..."
                                  className="flex-1 text-xs px-2.5 py-1.5 bg-white border border-blue-300 rounded-md focus:outline-none"
                                  autoFocus
                                />
                                <button
                                  type="submit"
                                  className="px-2.5 py-1.5 bg-slate-900 text-white rounded text-xs font-semibold cursor-pointer"
                                >
                                  Add
                                </button>
                                <button
                                  type="button"
                                  onClick={() => setAddingSubIngredientParentId(null)}
                                  className="px-2 py-1.5 text-xs text-slate-500 hover:text-slate-800 cursor-pointer"
                                >
                                  Cancel
                                </button>
                              </form>
                            ) : (
                              <button
                                type="button"
                                onClick={() => {
                                  setAddingSubIngredientParentId(node.id);
                                  setNewSubIngredientInput('');
                                }}
                                className="inline-flex items-center gap-1 text-[11px] font-semibold text-blue-700 hover:text-blue-900 cursor-pointer py-1"
                              >
                                <Plus className="w-3 h-3" />
                                <span>Add sub-ingredient to {node.name}</span>
                              </button>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Launch Analysis Action */}
          <div className="pt-4 border-t border-slate-200 flex flex-col sm:flex-row items-center justify-between gap-3">
            <span className="text-xs text-slate-500 text-center sm:text-left">
              Human review complete. Preserved {hierarchyCounts.topLevelCount} primary components ({hierarchyCounts.totalCount} total parsed items).
            </span>

            <button
              type="button"
              onClick={handleProceedToAnalysis}
              className="w-full sm:w-auto px-6 py-3 bg-slate-900 hover:bg-slate-800 text-white rounded-xl text-sm font-semibold flex items-center justify-center gap-2 shadow-md transition-all active:scale-[0.98] cursor-pointer min-h-[44px]"
            >
              <span>Analyze Ingredients ({hierarchyCounts.totalCount})</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </section>
      )}
    </div>
  );
};
