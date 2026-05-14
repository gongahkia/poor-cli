import { AIProvider } from '@/types/provider';

export interface ProviderRegistryEntry {
  id: AIProvider;
  label: string;
  defaultModel: string;
  keyUrl: string;
  keyPlaceholder: string;
  isLocal: boolean;
  defaultEndpoint?: string;
}

export const PROVIDER_REGISTRY: Record<AIProvider, ProviderRegistryEntry> = {
  gemini: {
    id: 'gemini',
    label: 'Gemini',
    defaultModel: 'gemini-2.0-flash-exp',
    keyUrl: 'https://aistudio.google.com/app/apikey',
    keyPlaceholder: 'Enter your Gemini API key',
    isLocal: false,
  },
  openai: {
    id: 'openai',
    label: 'OpenAI',
    defaultModel: 'gpt-4o',
    keyUrl: 'https://platform.openai.com/api-keys',
    keyPlaceholder: 'Enter your OpenAI API key',
    isLocal: false,
  },
  claude: {
    id: 'claude',
    label: 'Claude',
    defaultModel: 'claude-3-5-sonnet-20241022',
    keyUrl: 'https://console.anthropic.com/settings/keys',
    keyPlaceholder: 'Enter your Anthropic API key',
    isLocal: false,
  },
  ollama: {
    id: 'ollama',
    label: 'Ollama (Local)',
    defaultModel: 'llama3',
    keyUrl: 'https://ollama.com',
    keyPlaceholder: 'Enter Ollama Base URL (default: http://localhost:11434)',
    isLocal: true,
    defaultEndpoint: 'http://localhost:11434',
  },
  lmstudio: {
    id: 'lmstudio',
    label: 'LM Studio (Local)',
    defaultModel: 'local-model',
    keyUrl: 'https://lmstudio.ai',
    keyPlaceholder: 'Enter LM Studio Base URL (default: http://localhost:1234/v1)',
    isLocal: true,
    defaultEndpoint: 'http://localhost:1234',
  },
};

export const PROVIDER_IDS = Object.keys(PROVIDER_REGISTRY) as AIProvider[];
export const PROVIDER_LIST = PROVIDER_IDS.map((id) => PROVIDER_REGISTRY[id]);

export function getProviderRegistryEntry(provider: AIProvider): ProviderRegistryEntry {
  return PROVIDER_REGISTRY[provider];
}
