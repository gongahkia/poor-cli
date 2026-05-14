export interface Attachment {
  id: string;
  name: string;
  size: number;
  type?: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  toolCalls?: ToolCall[];
  citations?: Citation[];
  attachments?: Attachment[];
  responseTime?: number; // Time in milliseconds
  tokenCount?: number;
  cost?: number;
  parentId?: string;
  childrenIds?: string[];
}

export interface ToolCall {
  id: string;
  name: string;
  parameters: Record<string, any>;
  result?: any;
  status: 'pending' | 'success' | 'error';
}

export interface Citation {
  id: string;
  title: string;
  url: string;
  type: 'case' | 'statute' | 'regulation' | 'article';
  jurisdiction?: string;
  year?: number;
  citation_status?: 'valid' | 'incomplete' | 'malformed' | 'unverified';
  citation_confidence?: number;
}

export interface Artifact {
  id: string;
  type: 'text' | 'markdown';
  title: string;
  content: string;
  createdAt: number; // Timestamp
  messageId: string; // ID of the message that generated this artifact
}

export interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  nodeMap?: Record<string, Message>; // Full tree structure
  currentLeafId?: string; // Tip of current branch
  artifacts?: Artifact[];
  createdAt: Date;
  updatedAt: Date;
}

export interface ChatState {
  messages: Message[];
  nodeMap?: Record<string, Message>;
  currentLeafId?: string;
  artifacts: Artifact[];
  isLoading: boolean;
  currentProvider: string;
  settings: ChatSettings;
}

export interface ContextProfile {
  id: string;
  name: string;
  description?: string;
  userRole: string;
  userPurpose: string;
  systemPrompt?: string;
}

export interface Snippet {
  id: string;
  title: string;
  content: string;
  createdAt: number;
}

export interface ChatSettings {
  temperature: number;
  maxTokens: number;
  topP?: number;
  topK?: number;
  frequencyPenalty?: number;
  presencePenalty?: number;
  systemPrompt: string;
  autoSave: boolean;
  darkMode: boolean;
  agentMode: boolean;
  focusMode: boolean;
  userName?: string;
  userRole?: string;
  userPurpose?: string;
  profiles?: ContextProfile[];
  activeProfileId?: string;
  snippets?: Snippet[];
  theme?:
    | 'vanilla'
    | 'gruvbox'
    | 'everforest'
    | 'tokyo-night'
    | 'catppuccin'
    | 'solarized'
    | 'rose-pine'
    | 'kanagawa'
    | 'nord'
    | 'cyberpunk';
  asciiLogo?: string;
}

export type DiagramRenderer = 'mermaid' | 'plantuml' | 'graphviz' | 'd2';
