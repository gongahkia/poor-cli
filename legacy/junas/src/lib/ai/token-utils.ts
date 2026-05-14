// Token estimation (rough approximation: 1 token ≈ 4 characters)
export function estimateTokens(text: string): number {
  if (!text) return 0;
  return Math.ceil(text.length / 4);
}

// Cost per 1K tokens (as of 2024)
export type PricingInfo = { input: number; output: number };

export const PRICING: Record<string, Record<string, PricingInfo>> = {
  gemini: {
    'gemini-2.0-flash-exp': { input: 0, output: 0 }, // Free during preview
    'gemini-1.5-pro': { input: 0.00125, output: 0.005 },
  },
  openai: {
    'gpt-4o': { input: 0.0025, output: 0.01 },
    'gpt-4-turbo': { input: 0.01, output: 0.03 },
  },
  claude: {
    'claude-3-5-sonnet-20241022': { input: 0.003, output: 0.015 },
    'claude-3-opus-20240229': { input: 0.015, output: 0.075 },
  },
};

export function estimateCost(tokens: number, provider: string, model: string, type: 'input' | 'output' = 'output'): number {
  const providerPricing = PRICING[provider];
  if (!providerPricing) return 0;

  // Default to first model if exact match not found (simplified)
  const defaultModel = Object.keys(providerPricing)[0];
  const pricing: PricingInfo = providerPricing[model] || providerPricing[defaultModel] || { input: 0, output: 0 };
  
  return (tokens / 1000) * pricing[type];
}
