import type { GenerateResult, ProviderGenerateInput } from "../types";

type AnthropicResponse = {
  content?: Array<{ type: string; text?: string }>;
};

export async function generateAnthropic(input: ProviderGenerateInput): Promise<GenerateResult> {
  const response = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": input.apiKey,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model: input.model,
      system: input.system,
      max_tokens: input.maxTokens ?? 1200,
      temperature: input.temperature ?? 0.2,
      messages: [{ role: "user", content: input.prompt }],
    }),
  });

  if (!response.ok) {
    throw new Error(`Anthropic request failed: ${response.status}`);
  }

  const payload = (await response.json()) as AnthropicResponse;
  const text = (payload.content ?? [])
    .filter((block) => block.type === "text" && typeof block.text === "string")
    .map((block) => block.text)
    .join("\n")
    .trim();
  if (text === "") {
    throw new Error("Anthropic returned an empty response.");
  }

  return { provider: "anthropic", model: input.model, text };
}
