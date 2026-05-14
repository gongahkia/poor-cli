export type RiskLevel = 'HIGH' | 'MEDIUM' | 'LOW';
export interface RiskFlag {
  category: string;
  description: string;
  level: RiskLevel;
}
export interface RiskAssessment {
  flags: RiskFlag[];
  overall: RiskLevel;
  summary: string;
}

const RISK_CATEGORIES = [
  'Liability', 'Termination', 'Intellectual Property', 'Payment',
  'Confidentiality', 'Indemnification', 'Force Majeure', 'Governing Law',
  'Data Protection', 'Non-Compete', 'Warranty', 'Dispute Resolution',
];

const RISK_PATTERN = /(?:^|\n)\s*[-*•]?\s*\*?\*?([A-Za-z\s/&]+)\*?\*?\s*[-:]\s*(HIGH|MEDIUM|LOW)\b[^]*?(?=\n\s*[-*•]?\s*\*?\*?[A-Z]|\n\s*#{1,3}\s|\n\s*\d+\.\s|\Z)/gim;
const OVERALL_PATTERN = /(?:overall|aggregate|total)\s+risk[^:]*:\s*\*?\*?(HIGH|MEDIUM|LOW)\*?\*?/i;

export function parseRiskFromAIResponse(text: string): RiskAssessment {
  const flags: RiskFlag[] = [];
  // try structured pattern
  let match: RegExpExecArray | null;
  while ((match = RISK_PATTERN.exec(text)) !== null) {
    const rawCategory = match[1].trim().replace(/\*+/g, '');
    const level = match[2].toUpperCase() as RiskLevel;
    const category = fuzzyMatchCategory(rawCategory);
    const endIdx = match.index + match[0].length;
    const description = text.slice(match.index, endIdx).replace(/^[-*•\s]+/, '').trim();
    if (category) {
      flags.push({ category, description: description.slice(0, 300), level });
    }
  }
  // fallback: scan for "HIGH/MEDIUM/LOW" near known categories
  if (flags.length === 0) {
    for (const cat of RISK_CATEGORIES) {
      const catPattern = new RegExp(`${cat}[^\\n]*?(HIGH|MEDIUM|LOW)`, 'i');
      const m = text.match(catPattern);
      if (m) {
        flags.push({
          category: cat,
          description: m[0].trim(),
          level: m[1].toUpperCase() as RiskLevel,
        });
      }
    }
  }
  const overallMatch = text.match(OVERALL_PATTERN);
  const overall = overallMatch
    ? (overallMatch[1].toUpperCase() as RiskLevel)
    : computeOverallRisk(flags);
  return {
    flags,
    overall,
    summary: `${flags.length} risk areas identified. Overall risk: ${overall}.`,
  };
}

function fuzzyMatchCategory(raw: string): string | null {
  const lower = raw.toLowerCase();
  for (const cat of RISK_CATEGORIES) {
    if (lower.includes(cat.toLowerCase()) || cat.toLowerCase().includes(lower)) {
      return cat;
    }
  }
  if (lower.length > 2) return raw; // keep as custom category
  return null;
}

function computeOverallRisk(flags: RiskFlag[]): RiskLevel {
  if (flags.length === 0) return 'LOW';
  const highCount = flags.filter((f) => f.level === 'HIGH').length;
  const medCount = flags.filter((f) => f.level === 'MEDIUM').length;
  if (highCount >= 2) return 'HIGH';
  if (highCount >= 1 || medCount >= 3) return 'MEDIUM';
  return 'LOW';
}
