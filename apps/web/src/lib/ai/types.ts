export type AiProvider = "anthropic" | "openai" | "google";

export type GenerateInput = {
  provider: AiProvider;
  prompt: string;
  system?: string;
  model?: string;
  temperature?: number;
  maxTokens?: number;
};

export type ProviderGenerateInput = GenerateInput & {
  apiKey: string;
  model: string;
};

export type GenerateResult = {
  provider: AiProvider;
  model: string;
  text: string;
};

export type ProviderGenerate = (input: ProviderGenerateInput) => Promise<GenerateResult>;
