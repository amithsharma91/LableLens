/**
 * LabelLens — Structural Ingredient Parser
 * Parentheses-aware recursive parser for product packaging statements.
 * Preserves hierarchical ingredient trees, percentages, and additive codes (INS/E numbers).
 */

export interface RawParsedToken {
  name: string;
  rawText: string;
  percentage: number | null;
  identifier: string | null;
  subIngredientsString: string | null;
}

export interface ParsedIngredientNode {
  id: string;
  rawText: string;
  name: string;
  percentage: number | null;
  identifier: string | null;
  parentId: string | null;
  position: number;
  depth: number;
  children: ParsedIngredientNode[];
}

/**
 * Splits a text by commas / semicolons ONLY at depth 0 (outside parentheses/brackets/quotes).
 */
export function splitTopLevelDelimiters(text: string): string[] {
  const results: string[] = [];
  let current = '';
  let parenDepth = 0;
  let bracketDepth = 0;
  let braceDepth = 0;
  let inQuotes = false;
  let quoteChar = '';

  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    const prevChar = i > 0 ? text[i - 1] : '';

    // Handle quotes
    if ((char === '"' || char === "'") && prevChar !== '\\') {
      if (!inQuotes) {
        inQuotes = true;
        quoteChar = char;
      } else if (char === quoteChar) {
        inQuotes = false;
      }
      current += char;
      continue;
    }

    if (inQuotes) {
      current += char;
      continue;
    }

    // Handle nested grouping symbols
    if (char === '(') {
      parenDepth++;
    } else if (char === ')') {
      if (parenDepth > 0) parenDepth--;
    } else if (char === '[') {
      bracketDepth++;
    } else if (char === ']') {
      if (bracketDepth > 0) bracketDepth--;
    } else if (char === '{') {
      braceDepth++;
    } else if (char === '}') {
      if (braceDepth > 0) braceDepth--;
    }

    // Split on comma or semicolon only when at root depth (0)
    if ((char === ',' || char === ';') && parenDepth === 0 && bracketDepth === 0 && braceDepth === 0) {
      const trimmed = current.trim();
      if (trimmed.length > 0) {
        results.push(trimmed);
      }
      current = '';
    } else {
      current += char;
    }
  }

  const lastTrimmed = current.trim();
  if (lastTrimmed.length > 0) {
    results.push(lastTrimmed);
  }

  return results;
}

/**
 * Extracts top-level parenthetical groups from an ingredient segment string.
 * Example: "Peanut Butter (83%) (Peanut (68%), Jaggery Powder (14%), Salt)"
 * Returns the prefix name "Peanut Butter" and groups: ["83%", "Peanut (68%), Jaggery Powder (14%), Salt"]
 */
export function extractTopLevelParentheticalGroups(segment: string): {
  prefix: string;
  groups: string[];
} {
  let parenDepth = 0;
  let currentGroup = '';
  let prefix = '';
  const groups: string[] = [];
  let foundFirstParen = false;

  for (let i = 0; i < segment.length; i++) {
    const char = segment[i];

    if (char === '(' || char === '[') {
      if (parenDepth === 0) {
        foundFirstParen = true;
        currentGroup = '';
      } else {
        currentGroup += char;
      }
      parenDepth++;
    } else if (char === ')' || char === ']') {
      if (parenDepth > 0) {
        parenDepth--;
        if (parenDepth === 0) {
          groups.push(currentGroup.trim());
          currentGroup = '';
        } else {
          currentGroup += char;
        }
      }
    } else {
      if (parenDepth === 0 && !foundFirstParen) {
        prefix += char;
      } else if (parenDepth > 0) {
        currentGroup += char;
      }
    }
  }

  return {
    prefix: prefix.trim(),
    groups,
  };
}

/**
 * Checks if a string inside parentheses represents a percentage e.g. "83%", "14 %", "25.5%"
 */
export function parsePercentage(str: string): number | null {
  const match = str.trim().match(/^(\d+(?:\.\d+)?)\s*%$/);
  if (match) {
    return parseFloat(match[1]);
  }
  return null;
}

/**
 * Checks if a string inside parentheses represents an additive code e.g. "INS471", "INS 471", "E330", "E 415", "INS 322(i)"
 */
export function parseAdditiveIdentifier(str: string): string | null {
  const trimmed = str.trim();
  const match = trimmed.match(/^(INS|E|CI)\s*(\d+[a-z]?(?:\([a-z0-9]+\))?)$/i);
  if (match) {
    return `${match[1].toUpperCase()} ${match[2]}`.trim();
  }
  return null;
}

/**
 * Analyzes a single top-level segment to extract name, percentage, additive code, and sub-ingredients text.
 */
export function decomposeIngredientSegment(rawSegment: string): RawParsedToken {
  const { prefix, groups } = extractTopLevelParentheticalGroups(rawSegment);
  let name = prefix || rawSegment;
  let percentage: number | null = null;
  let identifier: string | null = null;
  let subIngredientsString: string | null = null;

  // Inspect each parenthetical group
  for (const group of groups) {
    // 1. Is it a percentage?
    const pct = parsePercentage(group);
    if (pct !== null && percentage === null) {
      percentage = pct;
      continue;
    }

    // 2. Is it an additive identifier like INS471 or E330?
    const code = parseAdditiveIdentifier(group);
    if (code !== null && identifier === null) {
      identifier = code;
      continue;
    }

    // 3. Does it contain sub-ingredients (has commas or multiple items)?
    if (group.includes(',') || group.includes(';')) {
      subIngredientsString = group;
      continue;
    }

    // 4. If single word or alias, e.g. "Aqua (Water)" or "Sunflower-derived"
    if (!subIngredientsString && !identifier) {
      // Check if it's an additive code without prefix
      const fallbackCode = group.match(/^(\d{3,4}[a-z]?)$/i);
      if (fallbackCode) {
        identifier = `INS ${fallbackCode[1]}`;
      } else {
        // If not code, could be sub-ingredient or specification
        subIngredientsString = group;
      }
    }
  }

  // Clean trailing punctuation from name
  name = name.replace(/[:\-]$/, '').trim();

  return {
    name,
    rawText: rawSegment.trim(),
    percentage,
    identifier,
    subIngredientsString,
  };
}

/**
 * Recursively parses a raw ingredient statement into a hierarchical tree.
 */
export function parseIngredientTree(
  rawText: string,
  parentId: string | null = null,
  depth: number = 0,
  idPrefix: string = 'node'
): ParsedIngredientNode[] {
  // Strip leading headers such as "INGREDIENTS:", "Ingredients Statement:", etc.
  let cleaned = rawText.trim();
  if (depth === 0) {
    cleaned = cleaned.replace(/^(INGREDIENTS|Active Ingredients|Contains|Composition)\s*[:\-]\s*/i, '');
  }

  const topLevelSegments = splitTopLevelDelimiters(cleaned);
  const nodes: ParsedIngredientNode[] = [];

  for (let i = 0; i < topLevelSegments.length; i++) {
    const segment = topLevelSegments[i];
    const decomposed = decomposeIngredientSegment(segment);
    const nodeId = `${idPrefix}_${depth}_${i + 1}_${Date.now()}`;

    let children: ParsedIngredientNode[] = [];
    if (decomposed.subIngredientsString) {
      children = parseIngredientTree(
        decomposed.subIngredientsString,
        nodeId,
        depth + 1,
        `${nodeId}_sub`
      );
    }

    nodes.push({
      id: nodeId,
      rawText: decomposed.rawText,
      name: decomposed.name,
      percentage: decomposed.percentage,
      identifier: decomposed.identifier,
      parentId,
      position: i + 1,
      depth,
      children,
    });
  }

  return nodes;
}

/**
 * Utility to count total components and top-level components in a parsed tree.
 */
export function getTreeHierarchyCounts(nodes: ParsedIngredientNode[]): {
  topLevelCount: number;
  nestedCount: number;
  totalCount: number;
} {
  const topLevelCount = nodes.length;
  let totalCount = 0;

  function countRecursive(list: ParsedIngredientNode[]) {
    for (const item of list) {
      totalCount++;
      if (item.children && item.children.length > 0) {
        countRecursive(item.children);
      }
    }
  }

  countRecursive(nodes);
  return {
    topLevelCount,
    nestedCount: Math.max(0, totalCount - topLevelCount),
    totalCount,
  };
}

/**
 * Serializes an ingredient tree node back into a canonical label segment.
 * Preserves parenthetical percentages, additive codes, and sub-ingredient lists.
 */
export function serializeIngredientNode(node: {
  name: string;
  rawText: string;
  percentage?: number | null;
  identifier?: string | null;
  children?: any[];
}): string {
  if (node.children && node.children.length > 0) {
    let prefix = node.name.replace(/\s*\([^)]*\)/g, '').trim();
    if (!prefix) prefix = node.name.trim();

    let result = prefix;
    if (node.percentage !== null && node.percentage !== undefined) {
      result += ` (${node.percentage}%)`;
    }
    if (node.identifier) {
      result += ` (${node.identifier})`;
    }
    const childrenStr = node.children.map(serializeIngredientNode).join(', ');
    result += ` (${childrenStr})`;
    return result;
  }
  return node.rawText;
}

/**
 * Serializes a list of top-level nodes into a full ingredients statement string.
 */
export function serializeIngredientTree(nodes: any[]): string {
  return nodes.map(serializeIngredientNode).join(', ');
}
