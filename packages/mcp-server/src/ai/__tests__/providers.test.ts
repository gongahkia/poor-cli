import { describe, expect, it } from "vitest";

import { resolveAiProviderConfig } from "../providers.js";

describe("AI provider config", () => {
  it("defaults to OpenAI and ignores browser-prefixed keys", () => {
    const config = resolveAiProviderConfig({
      VITE_OPENAI_API_KEY: "browser-secret",
    } as NodeJS.ProcessEnv);

    expect(config).toMatchObject({
      configured: false,
      model: "gpt-4o",
      provider: "openai",
      reason: {
        code: "AI_PROVIDER_UNCONFIGURED",
      },
    });
  });

  it("supports Anthropic, OpenAI, and Google server-side credentials", () => {
    expect(resolveAiProviderConfig({
      ANTHROPIC_API_KEY: "anthropic-key",
      DUDE_AI_PROVIDER: "anthropic",
    } as NodeJS.ProcessEnv)).toMatchObject({
      configured: true,
      provider: "anthropic",
    });

    expect(resolveAiProviderConfig({
      DUDE_AI_PROVIDER: "openai",
      OPENAI_API_KEY: "openai-key",
    } as NodeJS.ProcessEnv)).toMatchObject({
      configured: true,
      provider: "openai",
    });

    expect(resolveAiProviderConfig({
      DUDE_AI_PROVIDER: "google",
      GOOGLE_API_KEY: "google-key",
    } as NodeJS.ProcessEnv)).toMatchObject({
      configured: true,
      provider: "google",
    });
  });

  it("uses Azure OpenAI deployment env for OpenAI when present", () => {
    expect(resolveAiProviderConfig({
      DUDE_AI_PROVIDER: "openai",
      GPT5_MINI_API_KEY: "azure-key",
      GPT5_MINI_API_VERSION: "2025-04-01-preview",
      GPT5_MINI_DEPLOYMENT: "gpt-mini",
      GPT5_MINI_ENDPOINT: "https://example.openai.azure.com",
    } as NodeJS.ProcessEnv)).toMatchObject({
      azureOpenAi: {
        apiVersion: "2025-04-01-preview",
        deployment: "gpt-mini",
        endpoint: "https://example.openai.azure.com",
      },
      configured: true,
      model: "gpt-mini",
      provider: "openai",
    });
  });

  it("returns structured unavailable config for invalid provider selection", () => {
    expect(resolveAiProviderConfig({
      DUDE_AI_PROVIDER: "browser",
      OPENAI_API_KEY: "openai-key",
    } as NodeJS.ProcessEnv)).toMatchObject({
      configured: false,
      provider: "openai",
      reason: {
        code: "AI_PROVIDER_INVALID",
      },
    });
  });
});
