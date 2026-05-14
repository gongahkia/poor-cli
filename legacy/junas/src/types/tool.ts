export interface ToolDefinition {
  name: string;
  description: string;
  parameters: {
    type: 'object';
    properties: Record<string, {
      type: string;
      description: string;
      required?: boolean;
    }>;
    required?: string[];
  };
}

export interface ToolResult {
  success: boolean;
  data?: any;
  error?: string;
  metadata?: {
    processingTime: number;
    confidence?: number;
    source?: string;
  };
}

export interface OCRResult {
  text: string;
  confidence: number;
  boundingBoxes?: BoundingBox[];
}

export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
  text: string;
  confidence: number;
}

export interface NERResult {
  entities: {
    PERSON: string[];
    ORG: string[];
    DATE: string[];
    MONEY: string[];
    LAW: string[];
    GPE: string[];
  };
  confidence: number;
}

export interface ContractAnalysis {
  parties: string[];
  effectiveDate: string;
  term: string;
  paymentTerms: string[];
  terminationProvisions: string[];
  liabilityProvisions: string[];
  disputeResolution: string;
  governingLaw: string;
  riskFlags: RiskFlag[];
}

export interface RiskFlag {
  type: 'one-sided' | 'missing' | 'ambiguous' | 'unusual';
  description: string;
  severity: 'low' | 'medium' | 'high';
  clause?: string;
  suggestion?: string;
}

export interface LegalSearchResult {
  title: string;
  url: string;
  type: 'case' | 'statute' | 'regulation';
  jurisdiction: string;
  court?: string;
  year?: number;
  citation?: string;
  summary: string;
  relevanceScore: number;
}

export interface DocumentSummary {
  oneSentence: string;
  paragraph: string;
  keyPoints: string[];
  wordCount: number;
  readingTime: number;
}
