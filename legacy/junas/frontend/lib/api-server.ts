/**
 * Server-safe API client for Next.js server components.
 * Mirrors api-client.ts but uses process.env and {cache: "no-store"}.
 */
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
function apiUrl(path: string): string { return `${API_BASE}/api/v1${path}`; }

async function get(path: string) {
  try {
    const resp = await fetch(apiUrl(path), { cache: "no-store" });
    if (!resp.ok) return null;
    return resp.json();
  } catch { return null; }
}
async function post(path: string, body: any) {
  try {
    const resp = await fetch(apiUrl(path), { method: "POST", cache: "no-store", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!resp.ok) { const err = await resp.json().catch(() => ({})); return { error: (err as any).detail || `HTTP ${resp.status}` }; }
    return resp.json();
  } catch (e: any) { return { error: e.message || "Network error" }; }
}

// health
export async function getReady() { return (await get("/ready")) ?? { services: {} }; }
export async function getMetrics() { return await get("/metrics"); }

// glossary
export async function searchGlossary(q: string, jurisdiction = "", domain = "", page = 1, perPage = 20) {
  const params = new URLSearchParams({ q, page: String(page), per_page: String(perPage) });
  if (jurisdiction) params.set("jurisdiction", jurisdiction);
  if (domain) params.set("domain", domain);
  return (await get(`/glossary/search?${params}`)) ?? { results: [], total: 0 };
}
export async function getGlossaryTerm(phrase: string) { return await get(`/glossary/term/${encodeURIComponent(phrase)}`); }
export async function compareGlossaryTerm(term: string, jurisdictions?: string[]) {
  const params = new URLSearchParams({ term });
  if (jurisdictions) jurisdictions.forEach((j) => params.append("jurisdictions", j));
  return (await get(`/glossary/compare?${params}`)) ?? { comparisons: [] };
}
export async function suggestGlossary(prefix: string, size = 10) { return (await get(`/glossary/suggest?prefix=${encodeURIComponent(prefix)}&size=${size}`)) ?? { suggestions: [] }; }
export async function listGlossaryJurisdictions() { return (await get("/glossary/jurisdictions")) ?? { jurisdictions: [] }; }

// statutes
export async function searchStatutes(q: string, chapter = "", mode = "hybrid", page = 1, perPage = 20) {
  const params = new URLSearchParams({ q, mode, page: String(page), per_page: String(perPage) });
  if (chapter) params.set("chapter", chapter);
  return (await get(`/statutes/search?${params}`)) ?? { results: [], total: 0 };
}
export async function getStatuteSection(number: string) { return await get(`/statutes/section/${encodeURIComponent(number)}`); }
export async function listStatuteChapters() { return (await get("/statutes/chapters")) ?? { chapters: [] }; }
export async function getChapterSections(chapterNumber: string) { return await get(`/statutes/chapter/${encodeURIComponent(chapterNumber)}`); }

// search
export async function searchCases(query: string, topK = 10, stages = ["bm25", "dense", "rerank"], includeScores = true) {
  return await post("/search/cases", { query, top_k: topK, stages, include_scores: includeScores });
}
export async function listCharges() { return (await get("/search/charges")) ?? { charges: [] }; }
export async function getSearchMetrics() { return await get("/search/metrics"); }

// NER
export async function extractEntities(text: string, language = "en", granularity = "fine", useGazetteer = false) {
  return await post("/ner/extract", { text, language, granularity, use_gazetteer: useGazetteer });
}
export async function listEntityTypes() { return (await get("/ner/entity-types")) ?? { fine: {}, coarse: {} }; }

// contracts
export async function classifyContract(text: string, topK = 5) { return await post("/contracts/classify", { text, top_k_types: topK }); }
export async function scanToS(text: string, threshold = 0.5) { return await post("/contracts/scan-tos", { text, threshold }); }

// predictions
export async function predictScotus(text: string, topK = 5) { return await post("/predict/scotus", { text, top_k: topK }); }
export async function predictEcthr(text: string, task = "violation", threshold = 0.5) { return await post("/predict/ecthr", { text, task, threshold }); }
export async function predictCasehold(context: string, options: string[]) { return await post("/predict/casehold", { context, options }); }
export async function predictEurlex(text: string, threshold = 0.5, maxLabels = 10) { return await post("/predict/eurlex", { text, threshold, max_labels: maxLabels }); }

// research
export async function askResearch(question: string, sources?: string[], topK = 8, conversationId?: string) {
  return await post("/research/ask", { question, sources, top_k: topK, conversation_id: conversationId });
}
export async function getResearchConversation(conversationId: string) { return await get(`/research/conversations/${conversationId}`); }
export async function getResearchConfig() { return (await get("/research/config")) ?? { sources: [], model: "" }; }

// benchmarks
export async function listBenchmarkTasks() { return (await get("/benchmarks/tasks")) ?? { tasks: [] }; }
export async function listBenchmarkRuns(limit = 20) { return (await get(`/benchmarks/runs?limit=${limit}`)) ?? { runs: [] }; }
export async function getBenchmarkRun(runId: string) { return await get(`/benchmarks/runs/${runId}`); }
export async function getBenchmarkLeaderboard() { return (await get("/benchmarks/leaderboard")) ?? { leaderboard: [] }; }
export async function startBenchmarkRun(modelName: string, runName: string, tasks: string[], modelPath?: string) {
  return await post("/benchmarks/run", { model_name: modelName, run_name: runName, tasks, model_path: modelPath });
}

// rome statute
export async function searchRomeStatute(q: string, topK = 10) { return (await get(`/rome-statute/search?q=${encodeURIComponent(q)}&top_k=${topK}`)) ?? { results: [] }; }
export async function getRomeStatuteArticle(number: string | number) { return await get(`/rome-statute/article/${number}`); }
export async function listRomeStatuteParts() { return (await get("/rome-statute/parts")) ?? { parts: [] }; }
export async function getRomeStatutePart(number: string | number) { return await get(`/rome-statute/part/${number}`); }

// legal sources (SSO/CommonLII)
export async function searchSSO(query: string) { return (await get(`/legal-sources/sso?query=${encodeURIComponent(query)}`)) ?? []; }
