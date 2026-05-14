/**
 * Junas API client — replaces tauri-bridge.ts
 * All backend calls go through HTTP to the FastAPI backend.
 */
const API_BASE = typeof window !== "undefined"
  ? (window as any).__NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
  : process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function apiUrl(path: string): string {
  return `${API_BASE}/api/v1${path}`;
}

function getStoredApiKey(provider: string): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(`junas_apikey_${provider}`) || "";
}

export function setStoredApiKey(provider: string, key: string): void {
  if (typeof window === "undefined") return;
  if (key) localStorage.setItem(`junas_apikey_${provider}`, key);
  else localStorage.removeItem(`junas_apikey_${provider}`);
}

// streaming chat
export async function* chatStream(opts: {
  provider: string;
  model?: string;
  messages: { role: string; content: string }[];
  temperature?: number;
  maxTokens?: number;
  systemPrompt?: string;
  apiKey?: string;
  endpoint?: string;
}): AsyncGenerator<string> {
  const apiKey = opts.apiKey || getStoredApiKey(opts.provider);
  const resp = await fetch(apiUrl("/chat/stream"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      provider: opts.provider,
      model: opts.model || "",
      messages: opts.messages,
      temperature: opts.temperature,
      max_tokens: opts.maxTokens || 4096,
      system_prompt: opts.systemPrompt,
      api_key: apiKey,
      endpoint: opts.endpoint || "",
    }),
  });
  if (!resp.ok) throw new Error(`Chat failed: ${resp.status}`);
  const reader = resp.body?.getReader();
  if (!reader) return;
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      try {
        const event = JSON.parse(line.slice(6));
        if (event.error) throw new Error(event.error);
        if (event.delta) yield event.delta;
        if (event.done) return;
      } catch {}
    }
  }
}

// non-streaming chat
export async function chatSend(opts: {
  provider: string;
  model?: string;
  messages: { role: string; content: string }[];
  temperature?: number;
  maxTokens?: number;
  systemPrompt?: string;
  apiKey?: string;
}): Promise<{ content: string; model: string }> {
  const apiKey = opts.apiKey || getStoredApiKey(opts.provider);
  const resp = await fetch(apiUrl("/chat/send"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      provider: opts.provider, model: opts.model || "",
      messages: opts.messages, temperature: opts.temperature,
      max_tokens: opts.maxTokens || 4096, system_prompt: opts.systemPrompt,
      api_key: apiKey,
    }),
  });
  if (!resp.ok) throw new Error(`Chat failed: ${resp.status}`);
  return resp.json();
}

export async function listProviders() {
  const resp = await fetch(apiUrl("/chat/providers"));
  return resp.json();
}

// clauses
export async function listClauses(query = "", jurisdiction = "", category = "") {
  const params = new URLSearchParams();
  if (query) params.set("query", query);
  if (jurisdiction) params.set("jurisdiction", jurisdiction);
  if (category) params.set("category", category);
  const resp = await fetch(apiUrl(`/clauses?${params}`));
  return resp.json();
}

export async function getClause(id: string) {
  const resp = await fetch(apiUrl(`/clauses/${id}`));
  return resp.json();
}

// templates
export async function listTemplates(jurisdiction = "", category = "") {
  const params = new URLSearchParams();
  if (jurisdiction) params.set("jurisdiction", jurisdiction);
  if (category) params.set("category", category);
  const resp = await fetch(apiUrl(`/templates?${params}`));
  return resp.json();
}

export async function renderTemplate(id: string, values: Record<string, string>) {
  const resp = await fetch(apiUrl(`/templates/${id}/render`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ values }),
  });
  return resp.json();
}

// compliance
export async function checkCompliance(text: string, jurisdiction = "sg") {
  const resp = await fetch(apiUrl("/compliance/check"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, jurisdiction }),
  });
  return resp.json();
}

// documents
export async function parseDocument(file: File) {
  const form = new FormData();
  form.append("file", file);
  const resp = await fetch(apiUrl("/documents/parse"), { method: "POST", body: form });
  return resp.json();
}

// jurisdictions
export async function listJurisdictions() {
  const resp = await fetch(apiUrl("/jurisdictions"));
  return resp.json();
}

// legal sources
export async function searchSSO(query: string) {
  const resp = await fetch(apiUrl(`/legal-sources/sso?query=${encodeURIComponent(query)}`));
  return resp.json();
}

export async function searchCommonLII(query: string) {
  const resp = await fetch(apiUrl(`/legal-sources/commonlii?query=${encodeURIComponent(query)}`));
  return resp.json();
}

// compliance rules
export async function listComplianceRules(jurisdiction = "sg") {
  const resp = await fetch(apiUrl(`/compliance/rules?jurisdiction=${jurisdiction}`));
  return resp.json();
}

// glossary
export async function searchGlossary(q: string, jurisdiction = "", domain = "", page = 1, perPage = 20) {
  const params = new URLSearchParams({ q, page: String(page), per_page: String(perPage) });
  if (jurisdiction) params.set("jurisdiction", jurisdiction);
  if (domain) params.set("domain", domain);
  const resp = await fetch(apiUrl(`/glossary/search?${params}`));
  return resp.json();
}
export async function getGlossaryTerm(phrase: string) {
  const resp = await fetch(apiUrl(`/glossary/term/${encodeURIComponent(phrase)}`));
  return resp.json();
}
export async function compareGlossaryTerm(term: string, jurisdictions: string[]) {
  const params = new URLSearchParams({ term });
  jurisdictions.forEach((j) => params.append("jurisdictions", j));
  const resp = await fetch(apiUrl(`/glossary/compare?${params}`));
  return resp.json();
}
export async function suggestGlossary(prefix: string, size = 10) {
  const resp = await fetch(apiUrl(`/glossary/suggest?prefix=${encodeURIComponent(prefix)}&size=${size}`));
  return resp.json();
}
export async function listGlossaryJurisdictions() {
  const resp = await fetch(apiUrl("/glossary/jurisdictions"));
  return resp.json();
}

// statutes
export async function searchStatutes(q: string, chapter = "", mode = "hybrid", page = 1, perPage = 20) {
  const params = new URLSearchParams({ q, mode, page: String(page), per_page: String(perPage) });
  if (chapter) params.set("chapter", chapter);
  const resp = await fetch(apiUrl(`/statutes/search?${params}`));
  return resp.json();
}
export async function getStatuteSection(number: string) {
  const resp = await fetch(apiUrl(`/statutes/section/${encodeURIComponent(number)}`));
  return resp.json();
}
export async function listStatuteChapters() {
  const resp = await fetch(apiUrl("/statutes/chapters"));
  return resp.json();
}

// case retrieval
export async function searchCases(
  query: string,
  topK = 10,
  stages = ["bm25", "dense", "rerank"],
  includeScores = true,
) {
  const resp = await fetch(apiUrl("/search/cases"), {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, top_k: topK, stages, include_scores: includeScores }),
  });
  return resp.json();
}

// NER
export async function extractEntities(text: string, language = "en", granularity = "fine", useGazetteer = false) {
  const resp = await fetch(apiUrl("/ner/extract"), {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, language, granularity, use_gazetteer: useGazetteer }),
  });
  return resp.json();
}
export async function batchExtractEntities(texts: string[], language = "en") {
  const resp = await fetch(apiUrl("/ner/batch"), {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ texts, language }),
  });
  return resp.json();
}

// contracts
export async function classifyContract(text: string, topK = 5) {
  const resp = await fetch(apiUrl("/contracts/classify"), {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, top_k_types: topK }),
  });
  return resp.json();
}
export async function scanToS(text: string, threshold = 0.5) {
  const resp = await fetch(apiUrl("/contracts/scan-tos"), {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, threshold }),
  });
  return resp.json();
}

// predictions
export async function predictScotus(text: string, topK = 5) {
  const resp = await fetch(apiUrl("/predict/scotus"), {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, top_k: topK }),
  });
  return resp.json();
}
export async function predictEcthr(text: string, task = "violation", threshold = 0.5) {
  const resp = await fetch(apiUrl("/predict/ecthr"), {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, task, threshold }),
  });
  return resp.json();
}
export async function predictCasehold(context: string, options: string[]) {
  const resp = await fetch(apiUrl("/predict/casehold"), {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ context, options }),
  });
  return resp.json();
}
export async function predictEurlex(text: string, threshold = 0.5, maxLabels = 10) {
  const resp = await fetch(apiUrl("/predict/eurlex"), {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, threshold, max_labels: maxLabels }),
  });
  return resp.json();
}

// research (RAG)
export async function askResearch(question: string, sources?: string[], topK = 8, conversationId?: string) {
  const resp = await fetch(apiUrl("/research/ask"), {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, sources, top_k: topK, conversation_id: conversationId }),
  });
  return resp.json();
}
export async function getResearchConversation(conversationId: string) {
  const resp = await fetch(apiUrl(`/research/conversations/${conversationId}`));
  return resp.json();
}
export async function getResearchConfig() {
  const resp = await fetch(apiUrl("/research/config"));
  return resp.json();
}

// benchmarks
export async function startBenchmarkRun(modelName: string, runName: string, tasks: string[], modelPath?: string) {
  const resp = await fetch(apiUrl("/benchmarks/run"), {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model_name: modelName, run_name: runName, tasks, model_path: modelPath }),
  });
  return resp.json();
}
export async function listBenchmarkRuns(limit = 20) {
  const resp = await fetch(apiUrl(`/benchmarks/runs?limit=${limit}`));
  return resp.json();
}
export async function getBenchmarkRun(runId: string) {
  const resp = await fetch(apiUrl(`/benchmarks/runs/${runId}`));
  return resp.json();
}
export async function getBenchmarkLeaderboard() {
  const resp = await fetch(apiUrl("/benchmarks/leaderboard"));
  return resp.json();
}

// rome statute
export async function searchRomeStatute(q: string, topK = 10) {
  const resp = await fetch(apiUrl(`/rome-statute/search?q=${encodeURIComponent(q)}&top_k=${topK}`));
  return resp.json();
}
export async function getRomeStatuteArticle(number: number) {
  const resp = await fetch(apiUrl(`/rome-statute/article/${number}`));
  return resp.json();
}
export async function listRomeStatuteParts() {
  const resp = await fetch(apiUrl("/rome-statute/parts"));
  return resp.json();
}

// --- missing wrappers ---
export async function getClauseTone(clauseId: string, tone: string) {
  const resp = await fetch(apiUrl(`/clauses/${clauseId}/tone/${tone}`));
  return resp.json();
}
export async function getChapterSections(chapterNumber: string) {
  const resp = await fetch(apiUrl(`/statutes/chapter/${encodeURIComponent(chapterNumber)}`));
  return resp.json();
}
export async function getCaseDetails(caseId: string) {
  const resp = await fetch(apiUrl(`/search/cases/${encodeURIComponent(caseId)}`));
  return resp.json();
}
export async function listCharges() {
  const resp = await fetch(apiUrl("/search/charges"));
  return resp.json();
}
export async function listEntityTypes() {
  const resp = await fetch(apiUrl("/ner/entity-types"));
  return resp.json();
}
export async function listBenchmarkTasks() {
  const resp = await fetch(apiUrl("/benchmarks/tasks"));
  return resp.json();
}
export async function registerBenchmarkResult(payload: { model_name: string; run_name: string; task: string; micro_f1: number; macro_f1?: number }) {
  const resp = await fetch(apiUrl("/benchmarks/register"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  return resp.json();
}
export async function getRomeStatutePart(number: number) {
  const resp = await fetch(apiUrl(`/rome-statute/part/${number}`));
  return resp.json();
}
export async function deleteResearchConversation(conversationId: string) {
  const resp = await fetch(apiUrl(`/research/conversations/${conversationId}`), { method: "DELETE" });
  return resp.json();
}

// health
export async function getHealth() {
  const resp = await fetch(apiUrl("/health"));
  return resp.json();
}
export async function getReady() {
  const resp = await fetch(apiUrl("/ready"));
  return resp.json();
}
export async function getMetrics() {
  const resp = await fetch(apiUrl("/metrics"));
  return resp.json();
}
