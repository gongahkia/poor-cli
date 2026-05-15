import type { AiProvider, GenerateInput, GenerateResult, ProviderGenerate, ProviderGenerateInput } from "./types.js";

type ProviderDefinition = {
  readonly envVar: string;
  readonly modelEnvVar: string;
  readonly defaultModel: string;
  readonly generate: ProviderGenerate;
};

type ProviderConfigUnavailable = {
  readonly configured: false;
  readonly provider: AiProvider;
  readonly model: string;
  readonly reason: {
    readonly code: "AI_PROVIDER_UNCONFIGURED" | "AI_PROVIDER_INVALID";
    readonly message: string;
  };
};

type ProviderConfigReady = {
  readonly configured: true;
  readonly provider: AiProvider;
  readonly model: string;
  readonly apiKey: string;
};

export type ProviderConfig = ProviderConfigReady | ProviderConfigUnavailable;

type AnthropicResponse = {
  readonly content?: readonly { readonly type: string; readonly text?: string }[];
};

type GoogleResponse = {
  readonly candidates?: readonly { readonly content?: { readonly parts?: readonly { readonly text?: string }[] } }[];
};

type OpenAIResponse = {
  readonly choices?: readonly { readonly message?: { readonly content?: string } }[];
};

const generateAnthropic = async (input: ProviderGenerateInput): Promise<GenerateResult> => {
  const response = await fetch("https://api.anthropic.com/v1/messages", {
    body: JSON.stringify({
      max_tokens: input.maxTokens ?? 1200,
      messages: [{ role: "user", content: input.prompt }],
      model: input.model,
      system: input.system,
      temperature: input.temperature ?? 0.2,
    }),
    headers: {
      "Content-Type": "application/json",
      "anthropic-version": "2023-06-01",
      "x-api-key": input.apiKey,
    },
    method: "POST",
  });

  if (!response.ok) {
    throw new Error(`Anthropic request failed: ${response.status}`);
  }

  const payload = await response.json() as AnthropicResponse;
  const text = (payload.content ?? [])
    .filter((block) => block.type === "text" && typeof block.text === "string")
    .map((block) => block.text)
    .join("\n")
    .trim();
  if (text === "") {
    throw new Error("Anthropic returned an empty response.");
  }

  return { provider: "anthropic", model: input.model, text };
};

const generateGoogle = async (input: ProviderGenerateInput): Promise<GenerateResult> => {
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(input.model)}:generateContent?key=${encodeURIComponent(input.apiKey)}`;
  const response = await fetch(url, {
    body: JSON.stringify({
      contents: [{ role: "user", parts: [{ text: input.prompt }] }],
      generationConfig: {
        maxOutputTokens: input.maxTokens ?? 1200,
        temperature: input.temperature ?? 0.2,
      },
      system_instruction: input.system === undefined ? undefined : { parts: [{ text: input.system }] },
    }),
    headers: { "Content-Type": "application/json" },
    method: "POST",
  });

  if (!response.ok) {
    throw new Error(`Google request failed: ${response.status}`);
  }

  const payload = await response.json() as GoogleResponse;
  const text = (payload.candidates?.[0]?.content?.parts ?? [])
    .map((part) => part.text ?? "")
    .join("\n")
    .trim();
  if (text === "") {
    throw new Error("Google returned an empty response.");
  }

  return { provider: "google", model: input.model, text };
};

const generateOpenAI = async (input: ProviderGenerateInput): Promise<GenerateResult> => {
  const response = await fetch("https://api.openai.com/v1/chat/completions", {
    body: JSON.stringify({
      max_tokens: input.maxTokens ?? 1200,
      messages: [
        ...(input.system === undefined ? [] : [{ role: "system", content: input.system }]),
        { role: "user", content: input.prompt },
      ],
      model: input.model,
      temperature: input.temperature ?? 0.2,
    }),
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${input.apiKey}`,
    },
    method: "POST",
  });

  if (!response.ok) {
    throw new Error(`OpenAI request failed: ${response.status}`);
  }

  const payload = await response.json() as OpenAIResponse;
  const text = payload.choices?.[0]?.message?.content?.trim();
  if (text === undefined || text === "") {
    throw new Error("OpenAI returned an empty response.");
  }

  return { provider: "openai", model: input.model, text };
};

const PROVIDERS: Record<AiProvider, ProviderDefinition> = {
  anthropic: {
    defaultModel: "claude-3-5-sonnet-20241022",
    envVar: "ANTHROPIC_API_KEY",
    generate: generateAnthropic,
    modelEnvVar: "DUDE_ANTHROPIC_MODEL",
  },
  google: {
    defaultModel: "gemini-2.0-flash",
    envVar: "GOOGLE_API_KEY",
    generate: generateGoogle,
    modelEnvVar: "DUDE_GOOGLE_MODEL",
  },
  openai: {
    defaultModel: "gpt-4o",
    envVar: "OPENAI_API_KEY",
    generate: generateOpenAI,
    modelEnvVar: "DUDE_OPENAI_MODEL",
  },
};

const DEFAULT_PROVIDER: AiProvider = "openai";

const isProvider = (value: string): value is AiProvider =>
  value === "anthropic" || value === "openai" || value === "google";

const readOptional = (env: NodeJS.ProcessEnv, key: string): string | undefined => {
  const value = env[key]?.trim();
  return value === "" ? undefined : value;
};

export const resolveAiProviderConfig = (env: NodeJS.ProcessEnv = process.env): ProviderConfig => {
  const configuredProvider = readOptional(env, "DUDE_AI_PROVIDER") ?? DEFAULT_PROVIDER;
  if (!isProvider(configuredProvider)) {
    return {
      configured: false,
      model: readOptional(env, "DUDE_AI_MODEL") ?? "unknown",
      provider: DEFAULT_PROVIDER,
      reason: {
        code: "AI_PROVIDER_INVALID",
        message: "DUDE_AI_PROVIDER must be one of: openai, anthropic, google.",
      },
    };
  }

  const definition = PROVIDERS[configuredProvider];
  const model = readOptional(env, "DUDE_AI_MODEL")
    ?? readOptional(env, definition.modelEnvVar)
    ?? definition.defaultModel;
  const apiKey = readOptional(env, definition.envVar);
  if (apiKey === undefined) {
    return {
      configured: false,
      model,
      provider: configuredProvider,
      reason: {
        code: "AI_PROVIDER_UNCONFIGURED",
        message: `Set ${definition.envVar} on the REST gateway process to enable analyst memo generation.`,
      },
    };
  }

  return {
    apiKey,
    configured: true,
    model,
    provider: configuredProvider,
  };
};

export const generateText = async (
  input: Omit<GenerateInput, "provider" | "model">,
  config: ProviderConfigReady,
): Promise<GenerateResult> => {
  const definition = PROVIDERS[config.provider];
  return definition.generate({
    ...input,
    apiKey: config.apiKey,
    model: config.model,
    provider: config.provider,
  });
};

export type { AiProvider, GenerateResult };
