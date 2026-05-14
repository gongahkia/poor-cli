import type { GenerateResult, ProviderGenerateInput } from "../types";

type GoogleResponse = {
  candidates?: Array<{ content?: { parts?: Array<{ text?: string }> } }>;
};

export async function generateGoogle(input: ProviderGenerateInput): Promise<GenerateResult> {
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(input.model)}:generateContent?key=${encodeURIComponent(input.apiKey)}`;
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      system_instruction: input.system === undefined ? undefined : { parts: [{ text: input.system }] },
      contents: [{ role: "user", parts: [{ text: input.prompt }] }],
      generationConfig: {
        temperature: input.temperature ?? 0.2,
        maxOutputTokens: input.maxTokens ?? 1200,
      },
    }),
  });

  if (!response.ok) {
    throw new Error(`Google request failed: ${response.status}`);
  }

  const payload = (await response.json()) as GoogleResponse;
  const text = (payload.candidates?.[0]?.content?.parts ?? [])
    .map((part) => part.text ?? "")
    .join("\n")
    .trim();
  if (text === "") {
    throw new Error("Google returned an empty response.");
  }

  return { provider: "google", model: input.model, text };
}
