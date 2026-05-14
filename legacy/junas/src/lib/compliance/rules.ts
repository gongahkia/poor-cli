export type ComplianceStatus = 'pass' | 'warning' | 'fail' | 'unchecked';
export interface ComplianceRule {
  id: string;
  name: string;
  category: string;
  description: string;
  keywords: string[];
  severity: 'high' | 'medium' | 'low';
}
export interface ComplianceCheckResult {
  ruleId: string;
  ruleName: string;
  status: ComplianceStatus;
  details: string;
  severity: 'high' | 'medium' | 'low';
}

export const DEFAULT_SG_RULES: ComplianceRule[] = [
  {
    id: 'pdpa-consent',
    name: 'PDPA Consent Clause',
    category: 'Data Protection',
    description: 'Document must reference consent for personal data collection under PDPA',
    keywords: ['consent', 'personal data', 'pdpa', 'data protection'],
    severity: 'high',
  },
  {
    id: 'pdpa-purpose',
    name: 'PDPA Purpose Limitation',
    category: 'Data Protection',
    description: 'Data usage purpose must be clearly stated',
    keywords: ['purpose', 'personal data', 'collection', 'use', 'disclosure'],
    severity: 'high',
  },
  {
    id: 'governing-law',
    name: 'Governing Law Clause',
    category: 'General',
    description: 'Contract must specify governing law',
    keywords: ['governing law', 'governed by', 'laws of'],
    severity: 'medium',
  },
  {
    id: 'dispute-resolution',
    name: 'Dispute Resolution',
    category: 'General',
    description: 'Contract must include dispute resolution mechanism',
    keywords: ['dispute resolution', 'arbitration', 'mediation', 'jurisdiction'],
    severity: 'medium',
  },
  {
    id: 'termination',
    name: 'Termination Clause',
    category: 'General',
    description: 'Contract must include termination provisions',
    keywords: ['termination', 'terminate', 'notice period'],
    severity: 'medium',
  },
  {
    id: 'indemnification',
    name: 'Indemnification',
    category: 'Liability',
    description: 'Indemnification provisions should be present',
    keywords: ['indemnify', 'indemnification', 'hold harmless'],
    severity: 'low',
  },
  {
    id: 'force-majeure',
    name: 'Force Majeure',
    category: 'Risk',
    description: 'Force majeure clause should be present for risk allocation',
    keywords: ['force majeure', 'act of god', 'unforeseeable', 'beyond control'],
    severity: 'low',
  },
  {
    id: 'confidentiality',
    name: 'Confidentiality',
    category: 'General',
    description: 'Confidentiality obligations should be specified',
    keywords: ['confidential', 'confidentiality', 'non-disclosure', 'proprietary'],
    severity: 'medium',
  },
  {
    id: 'employment-act-notice',
    name: 'Employment Act Notice Period',
    category: 'Employment',
    description: 'Employment contracts must comply with notice period requirements',
    keywords: ['notice period', 'termination notice', 'employment act'],
    severity: 'high',
  },
  {
    id: 'cpf-contribution',
    name: 'CPF Contribution Reference',
    category: 'Employment',
    description: 'Employment contracts should reference CPF obligations',
    keywords: ['cpf', 'central provident fund', 'employer contribution'],
    severity: 'medium',
  },
];

export function checkCompliance(text: string, rules: ComplianceRule[]): ComplianceCheckResult[] {
  const lower = text.toLowerCase();
  return rules.map((rule) => {
    const matchCount = rule.keywords.filter((kw) => lower.includes(kw.toLowerCase())).length;
    const ratio = matchCount / rule.keywords.length;
    let status: ComplianceStatus;
    let details: string;
    if (ratio >= 0.5) {
      status = 'pass';
      details = `Found ${matchCount}/${rule.keywords.length} expected keywords`;
    } else if (ratio > 0) {
      status = 'warning';
      details = `Partial match: ${matchCount}/${rule.keywords.length} keywords found`;
    } else {
      status = 'fail';
      details = `No matching keywords found — ${rule.description}`;
    }
    return { ruleId: rule.id, ruleName: rule.name, status, details, severity: rule.severity };
  });
}

const STORAGE_KEY = 'junas_compliance_rules';
export function loadCustomRules(): ComplianceRule[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    return JSON.parse(raw) as ComplianceRule[];
  } catch { return []; }
}
export function saveCustomRules(rules: ComplianceRule[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(rules));
}
