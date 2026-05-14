export type AIProvider = 'gemini' | 'openai' | 'claude' | 'ollama' | 'lmstudio';

export interface ProviderConfig {
  name: string;
  displayName: string;
  apiKey: string;
  model: string;
  maxTokens: number;
  temperature: number;
  enabled: boolean;
}

export interface ProviderResponse {
  content: string;
  usage?: {
    promptTokens: number;
    completionTokens: number;
    totalTokens: number;
  };
  model: string;
  finishReason?: string;
}

export interface StreamingResponse {
  content: string;
  done: boolean;
  usage?: {
    promptTokens: number;
    completionTokens: number;
    totalTokens: number;
  };
}

export interface ProviderToolCall {
  name: string;
  parameters: Record<string, any>;
}

export interface ProviderCapabilities {
  supportsStreaming: boolean;
  supportsFunctionCalling: boolean;
  supportsVision: boolean;
  maxContextLength: number;
  availableModels: string[];
}

export interface ProviderError {
  code: string;
  message: string;
  status?: number;
  retryable: boolean;
}
