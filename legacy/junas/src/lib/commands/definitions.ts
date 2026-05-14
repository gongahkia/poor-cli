export type CommandType =
  | 'extract-entities'
  | 'analyze-document'
  | 'summarize-local'
  | 'ner-advanced'
  | 'classify-text'
  | 'search-case-law'
  | 'research-statute'
  | 'analyze-contract'
  | 'summarize-document'
  | 'draft-clause'
  | 'check-compliance'
  | 'due-diligence-review'
  | 'generate-document'
  | 'use-template'
  | 'redline'
  | 'fetch-url'
  | 'web-search';

export type CommandCategory = 'research' | 'analysis' | 'drafting' | 'tools';

export interface CommandInfo {
  id: CommandType;
  label: string;
  description: string;
  category: CommandCategory;
  isLocal: boolean; // true = processed locally, false = requires AI
  requiresOnnx?: boolean;
  implemented: boolean;
}

export interface ProcessedCommand {
  command: CommandType;
  args: string;
  isLocal: boolean;
}

export interface LocalCommandResult {
  success: boolean;
  content: string;
  requiresModel?: string; // Model ID required for this command
  artifact?: {
    title: string;
    type: 'text' | 'markdown';
    content: string;
  };
}

export interface AsyncLocalCommandResult {
  success: boolean;
  content: string;
}

export const COMMANDS: CommandInfo[] = [
  {
    id: 'extract-entities',
    label: 'extract-entities',
    description: 'Identify persons, organizations, dates, and legal references (Local)',
    category: 'analysis',
    isLocal: true,
    implemented: true,
  },
  {
    id: 'analyze-document',
    label: 'analyze-document',
    description: 'Get document statistics, readability, and structure (Local)',
    category: 'analysis',
    isLocal: true,
    implemented: true,
  },
  {
    id: 'summarize-local',
    label: 'summarize-local',
    description: 'Summarize text using local ONNX model (requires download)',
    category: 'analysis',
    isLocal: true,
    requiresOnnx: true,
    implemented: true,
  },
  {
    id: 'ner-advanced',
    label: 'ner-advanced',
    description: 'Advanced NER using BERT model (requires download)',
    category: 'analysis',
    isLocal: true,
    requiresOnnx: true,
    implemented: true,
  },
  {
    id: 'classify-text',
    label: 'classify-text',
    description: 'Classify text sentiment using local model (requires download)',
    category: 'analysis',
    isLocal: true,
    requiresOnnx: true,
    implemented: true,
  },
  {
    id: 'search-case-law',
    label: 'search-case-law',
    description: 'Search Singapore legal database for relevant cases',
    category: 'research',
    isLocal: false,
    implemented: true,
  },
  {
    id: 'research-statute',
    label: 'research-statute',
    description: 'Look up statutory provisions and interpretations',
    category: 'research',
    isLocal: false,
    implemented: true,
  },
  {
    id: 'analyze-contract',
    label: 'analyze-contract',
    description: 'Extract key terms, obligations, and risks from contract',
    category: 'analysis',
    isLocal: false,
    implemented: true,
  },
  {
    id: 'summarize-document',
    label: 'summarize-document',
    description: 'Generate concise summary of legal document',
    category: 'analysis',
    isLocal: false,
    implemented: true,
  },
  {
    id: 'draft-clause',
    label: 'draft-clause',
    description: 'Generate legal clause based on requirements',
    category: 'drafting',
    isLocal: false,
    implemented: true,
  },
  {
    id: 'check-compliance',
    label: 'check-compliance',
    description: 'Verify regulatory compliance for Singapore law',
    category: 'tools',
    isLocal: false,
    implemented: true,
  },
  {
    id: 'due-diligence-review',
    label: 'due-diligence-review',
    description: 'Conduct legal due diligence checklist',
    category: 'analysis',
    isLocal: false,
    implemented: true,
  },
  {
    id: 'generate-document',
    label: 'generate-document',
    description: 'Generate a downloadable text or markdown document',
    category: 'tools',
    isLocal: true, // Processed locally to save the artifact
    implemented: true,
  },
  {
    id: 'use-template',
    label: 'use-template',
    description: 'Open the legal document template library',
    category: 'tools',
    isLocal: true,
    implemented: true,
  },
  {
    id: 'redline',
    label: 'redline',
    description: 'Compare two contract versions with tracked changes',
    category: 'tools',
    isLocal: true,
    implemented: true,
  },
  {
    id: 'fetch-url',
    label: 'fetch-url',
    description: 'Fetch and extract text content from a URL',
    category: 'research',
    isLocal: true,
    implemented: true,
  },
  {
    id: 'web-search',
    label: 'web-search',
    description: 'Search the web for information',
    category: 'research',
    isLocal: true,
    implemented: true,
  },
];
