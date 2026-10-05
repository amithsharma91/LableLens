import {
  Domain,
  IngredientNode,
  IngredientObservation,
  MatchStatus,
} from '../types/index';
import { DEMO_CHEMICAL_ENTITIES } from '../data/chemicalEntities';
import { parseIngredientTree, ParsedIngredientNode, getTreeHierarchyCounts } from './parsing/ingredientParser';
import { normalizeIngredientSyntax } from './normalization/ingredientNormalizer';
import { resolveEntity } from './entity-resolution/entityResolver';
import { computeConfidenceDimensions } from './confidence/confidenceModel';
import { generateWhyIsThisHereExplanation } from './explanation/explanationGenerator';
import { researchIngredientWithFallback } from '../services/webResearchService';

export interface PipelineOutput {
  tree: IngredientNode[];
  flattened: IngredientObservation[];
  counts: {
    topLevelCount: number;
    nestedCount: number;
    totalCount: number;
  };
}

/**
 * Transforms a ParsedIngredientNode into an enriched IngredientNode.
 */
function enrichNodeRecursive(
  parsed: ParsedIngredientNode,
  domain: Domain,
  overallOcrConfidence: string = 'High'
): IngredientNode {
  const hasChildren = parsed.children && parsed.children.length > 0;

  // 1. Syntactic Normalization
  const norm = normalizeIngredientSyntax(
    parsed.name,
    parsed.rawText,
    parsed.percentage,
    parsed.identifier
  );

  // 2. Entity Resolution
  const resolved = resolveEntity(
    norm.cleanKey,
    norm.identifier,
    norm.name,
    hasChildren
  );

  const hasTypo = norm.cleanKey === 'emulsifer';

  // 3. Multi-dimensional Confidence Computation
  const conf = computeConfidenceDimensions({
    rawText: parsed.rawText,
    classification: resolved.classification,
    matchStatus: resolved.matchStatus,
    hasAdditiveIdentifier: resolved.isAdditiveCodeMatched,
    hasTypo,
    isMixture: resolved.classification === 'KNOWN_COMPLEX_MIXTURE' || resolved.classification === 'KNOWN_FORMULATION_COMPONENT',
    chemicalEntityId: resolved.chemicalEntityId,
    overallOcrConfidence,
  });

  // 4. Targeted Explanation Generation
  const entity = resolved.chemicalEntityId ? DEMO_CHEMICAL_ENTITIES[resolved.chemicalEntityId] || null : null;
  const why = resolved.webResearch ? {
    whatIsIt: resolved.webResearch.summary,
    whyUsed: resolved.webResearch.whyUsed,
    relevantChemistry: resolved.webResearch.relevantChemistry,
    evidenceSupport: resolved.webResearch.evidenceSupport,
    uncertainties: resolved.webResearch.uncertainties,
  } : generateWhyIsThisHereExplanation({
    ingredientName: norm.name,
    classification: resolved.classification,
    entity,
    role: resolved.role,
    domain,
    identifier: norm.identifier,
    evidenceIds: resolved.evidenceIds,
    hasChildren,
  });

  // 5. Recursively enrich children
  const enrichedChildren = parsed.children.map(child =>
    enrichNodeRecursive(child, domain, overallOcrConfidence)
  );

  return {
    id: parsed.id,
    rawText: parsed.rawText,
    name: norm.name,
    normalizedName: resolved.canonicalName || norm.normalizedName,
    percentage: norm.percentage,
    identifier: norm.identifier,
    parentId: parsed.parentId,
    position: parsed.position,
    depth: parsed.depth,
    children: enrichedChildren,
    classification: resolved.classification,
    matchStatus: resolved.matchStatus,
    chemicalEntityId: resolved.chemicalEntityId,
    role: resolved.role,
    confidence: conf.confidence,
    confidenceScore: conf.confidenceScore,
    confidenceBreakdown: conf.breakdown,
    evidenceIds: resolved.evidenceIds,
    whyIsThisHere: why,
    verificationStatus: resolved.verificationStatus,
    webResearch: resolved.webResearch || undefined,
  };
}

/**
 * Flattens an ingredient tree for lists, counters, and backward compatibility.
 */
export function flattenIngredientTree(nodes: IngredientNode[]): IngredientObservation[] {
  const result: IngredientObservation[] = [];

  function walk(list: IngredientNode[]) {
    for (const node of list) {
      result.push({
        id: node.id,
        rawText: node.rawText,
        normalizedText: node.percentage ? `${node.name} (${node.percentage}%)` : node.name,
        matchStatus: node.matchStatus,
        chemicalEntityId: node.chemicalEntityId,
        role: node.role,
        confidence: node.confidence,
        confidenceScore: node.confidenceScore,
        evidenceIds: node.evidenceIds,
        whyIsThisHere: node.whyIsThisHere,
        isCustomEdited: node.isCustomEdited,
        parentId: node.parentId,
        depth: node.depth,
        percentage: node.percentage,
        identifier: node.identifier,
        classification: node.classification,
        confidenceBreakdown: node.confidenceBreakdown,
        childrenCount: node.children ? node.children.length : 0,
        verificationStatus: node.verificationStatus,
        webResearch: node.webResearch,
      });

      if (node.children && node.children.length > 0) {
        walk(node.children);
      }
    }
  }

  walk(nodes);
  return result;
}

/**
 * Main pipeline entry point: converts raw label text into an enriched tree and flattened observations.
 */
export function processIngredientsPipeline(
  rawText: string,
  domain: Domain = 'Food',
  overallOcrConfidence: string = 'High'
): PipelineOutput {
  const parsedTree = parseIngredientTree(rawText);
  const hierarchyCounts = getTreeHierarchyCounts(parsedTree);

  const enrichedTree = parsedTree.map(node =>
    enrichNodeRecursive(node, domain, overallOcrConfidence)
  );

  const flattened = flattenIngredientTree(enrichedTree);

  return {
    tree: enrichedTree,
    flattened,
    counts: hierarchyCounts,
  };
}

/**
 * Recursively researches ingredients that are missing from the local catalog and not yet verified in cache.
 * Updates nodes in-place with web-grounded research, sources, and provenance records.
 */
export async function resolveTreeWithWebResearch(
  tree: IngredientNode[],
  domain: Domain = 'Food',
  onProgress?: (message: string) => void
): Promise<IngredientNode[]> {
  async function processNode(node: IngredientNode): Promise<IngredientNode> {
    let updatedNode = { ...node };

    // If node is not locally verified and lacks webResearch, trigger research
    if (updatedNode.verificationStatus !== 'LOCAL_VERIFIED' && !updatedNode.webResearch) {
      if (onProgress) {
        onProgress(`Researching ingredient: ${updatedNode.name}...`);
      }
      const outcome = await researchIngredientWithFallback({
        ingredientName: updatedNode.name,
        rawText: updatedNode.rawText,
        identifier: updatedNode.identifier,
        domain,
      });

      if (outcome.webResearch) {
        updatedNode.webResearch = outcome.webResearch;
        updatedNode.verificationStatus = outcome.verificationStatus;
        updatedNode.role = outcome.webResearch.functionalRole || updatedNode.role;
        updatedNode.classification = outcome.webResearch.entityType;
        updatedNode.confidence = outcome.webResearch.confidenceLevel;
        updatedNode.confidenceScore = outcome.webResearch.confidenceScore;
        updatedNode.whyIsThisHere = {
          whatIsIt: outcome.webResearch.summary,
          whyUsed: outcome.webResearch.whyUsed,
          relevantChemistry: outcome.webResearch.relevantChemistry,
          evidenceSupport: outcome.webResearch.evidenceSupport,
          uncertainties: outcome.webResearch.uncertainties,
        };
      } else if (outcome.error) {
        updatedNode.verificationStatus = 'UNRESOLVED_UNKNOWN';
        updatedNode.researchError = outcome.error;
      }
    }

    if (updatedNode.children && updatedNode.children.length > 0) {
      const updatedChildren: IngredientNode[] = [];
      for (const child of updatedNode.children) {
        updatedChildren.push(await processNode(child));
      }
      updatedNode.children = updatedChildren;
    }

    return updatedNode;
  }

  const result: IngredientNode[] = [];
  for (const rootNode of tree) {
    result.push(await processNode(rootNode));
  }
  return result;
}
