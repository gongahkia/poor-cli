import type { GenerateResult, ProviderGenerateInput } from "../types";

type OpenAIResponse = {
  choices?: Array<{ message?: { content?: string } }>;
};

export async function generateOpenAI(input: ProviderGenerateInput): Promise<GenerateResult> {
  const response = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${input.apiKey}`,
    },
    body: JSON.stringify({
      model: input.model,
      messages: [
        ...(input.system === undefined ? [] : [{ role: "system", content: input.system }]),
        { role: "user", content: input.prompt },
      ],
      temperature: input.temperature ?? 0.2,
      max_tokens: input.maxTokens ?? 1200,
    }),
  });

  if (!response.ok) {
    throw new Error(`OpenAI request failed: ${response.status}`);
  }

  const payload = (await response.json()) as OpenAIResponse;
  const text = payload.choices?.[0]?.message?.content?.trim();
  if (text === undefined || text === "") {
    throw new Error("OpenAI returned an empty response.");
  }

  return { provider: "openai", model: input.model, text };
}
