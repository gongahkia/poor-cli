import { AIProvider, ProviderConfig } from '@/types/provider';
import {
  getProviderRegistryEntry,
  PROVIDER_IDS,
  PROVIDER_REGISTRY,
} from '@/lib/providers/registry';
export class ProviderFactory {
  static getAvailableProviders(): AIProvider[] {
    return PROVIDER_IDS;
  }
  static getDefaultConfig(provider: AIProvider): Partial<ProviderConfig> {
    const baseConfig = { temperature: 0.7, maxTokens: 4000, enabled: true };
    const providerEntry = getProviderRegistryEntry(provider);
    switch (provider) {
      case 'gemini':
        return {
          ...baseConfig,
          name: 'gemini',
          displayName: 'Google Gemini',
          model: providerEntry.defaultModel,
        };
      case 'openai':
        return {
          ...baseConfig,
          name: 'openai',
          displayName: 'OpenAI GPT',
          model: providerEntry.defaultModel,
        };
      case 'claude':
        return {
          ...baseConfig,
          name: 'claude',
          displayName: 'Anthropic Claude',
          model: providerEntry.defaultModel,
        };
      case 'ollama':
        return {
          ...baseConfig,
          name: 'ollama',
          displayName: 'Ollama (Local)',
          model: providerEntry.defaultModel,
          apiKey: PROVIDER_REGISTRY.ollama.defaultEndpoint || 'http://localhost:11434',
        };
      case 'lmstudio':
        return {
          ...baseConfig,
          name: 'lmstudio',
          displayName: 'LM Studio (Local)',
          model: providerEntry.defaultModel,
          apiKey: `${PROVIDER_REGISTRY.lmstudio.defaultEndpoint || 'http://localhost:1234'}/v1`,
        };
      default:
        throw new Error(`Unsupported provider: ${provider}`);
    }
  }
  static validateConfig(config: ProviderConfig): { valid: boolean; errors: string[] } {
    const errors: string[] = [];
    if (!config.name) errors.push('Provider name is required');
    if (
      config.name !== 'ollama' &&
      config.name !== 'lmstudio' &&
      (!config.apiKey || config.apiKey.trim() === '')
    )
      errors.push('API key is required');
    if (!config.model || config.model.trim() === '') errors.push('Model is required');
    if (config.temperature < 0 || config.temperature > 2)
      errors.push('Temperature must be between 0 and 2');
    if (config.maxTokens < 1 || config.maxTokens > 100000)
      errors.push('Max tokens must be between 1 and 100,000');
    return { valid: errors.length === 0, errors };
  }
}
