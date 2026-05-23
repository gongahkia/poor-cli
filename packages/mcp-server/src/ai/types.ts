export type AiProvider = "anthropic" | "openai" | "google";

export type GenerateInput = {
  readonly provider: AiProvider;
  readonly prompt: string;
  readonly system?: string;
  readonly model?: string;
  readonly temperature?: number;
  readonly maxTokens?: number;
  readonly responseFormat?: "json_object";
};

export type ProviderGenerateInput = GenerateInput & {
  readonly apiKey: string;
  readonly model: string;
  readonly azureOpenAi?: {
    readonly endpoint: string;
    readonly deployment: string;
    readonly apiVersion: string;
  };
};

export type GenerateResult = {
  readonly provider: AiProvider;
  readonly model: string;
  readonly text: string;
};

export type ProviderGenerate = (input: ProviderGenerateInput) => Promise<GenerateResult>;
