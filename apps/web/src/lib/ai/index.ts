import { generateAnthropic } from "./providers/anthropic";
import { generateGoogle } from "./providers/google";
import { generateOpenAI } from "./providers/openai";
import type { AiProvider, GenerateInput, GenerateResult, ProviderGenerate } from "./types";

const PROVIDERS: Record<AiProvider, { env: string; defaultModel: string; generate: ProviderGenerate }> = {
  anthropic: {
    env: "ANTHROPIC_API_KEY",
    defaultModel: "claude-3-5-sonnet-20241022",
    generate: generateAnthropic,
  },
  openai: {
    env: "OPENAI_API_KEY",
    defaultModel: "gpt-4o",
    generate: generateOpenAI,
  },
  google: {
    env: "GOOGLE_API_KEY",
    defaultModel: "gemini-2.0-flash",
    generate: generateGoogle,
  },
};

function readEnv(name: string): string {
  const value = process.env[name];
  if (value === undefined || value.trim() === "") {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

export async function generate(input: GenerateInput): Promise<GenerateResult> {
  // TODO: Wire this server-side scaffold into the future AI synthesis tier.
  if (typeof window !== "undefined") {
    throw new Error("AI generation must run server-side.");
  }

  const provider = PROVIDERS[input.provider];
  return provider.generate({
    ...input,
    apiKey: readEnv(provider.env),
    model: input.model ?? provider.defaultModel,
  });
}

export type { AiProvider, GenerateInput, GenerateResult };
