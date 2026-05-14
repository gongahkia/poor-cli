import { toErrorWithCode } from '@/lib/tauri-error';
import { isTauriRuntime } from '@/lib/runtime';

export interface Message {
  role: string;
  content: string;
}

export interface ChatSettings {
  temperature?: number;
  max_tokens?: number;
  top_p?: number;
  system_prompt?: string;
}

export interface ProviderResponse {
  content: string;
  model: string;
  usage?: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number };
}

export interface StreamChunk {
  delta: string;
  done: boolean;
}

export interface SearchResult {
  title: string;
  url: string;
  snippet: string;
}

type UnlistenFn = () => void;

interface OpenAIStyleResponse {
  choices?: Array<{ message?: { content?: string } }>;
  usage?: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number };
}

const MAX_FETCH_TEXT_CHARS = 50_000;

// --- encrypted localStorage for API keys ---
const CRYPTO_SALT = new Uint8Array([74,85,78,65,83,95,75,69,89,95,83,65,76,84,95,86]); // fixed app salt
const CRYPTO_IV_LEN = 12;
let cryptoKeyCache: CryptoKey | null = null;

async function getCryptoKey(): Promise<CryptoKey> {
  if (cryptoKeyCache) return cryptoKeyCache;
  const origin = typeof window !== 'undefined' ? window.location.origin : 'junas-app';
  const raw = new TextEncoder().encode(`junas_key_enc_${origin}`);
  const base = await crypto.subtle.importKey('raw', raw, 'PBKDF2', false, ['deriveKey']);
  cryptoKeyCache = await crypto.subtle.deriveKey(
    { name: 'PBKDF2', salt: CRYPTO_SALT, iterations: 100_000, hash: 'SHA-256' },
    base,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt'],
  );
  return cryptoKeyCache;
}

async function encryptString(plaintext: string): Promise<string> {
  const key = await getCryptoKey();
  const iv = crypto.getRandomValues(new Uint8Array(CRYPTO_IV_LEN));
  const encoded = new TextEncoder().encode(plaintext);
  const cipherBuf = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, encoded);
  const combined = new Uint8Array(iv.length + cipherBuf.byteLength);
  combined.set(iv, 0);
  combined.set(new Uint8Array(cipherBuf), iv.length);
  return btoa(String.fromCharCode(...combined));
}

async function decryptString(b64: string): Promise<string> {
  const key = await getCryptoKey();
  const raw = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  const iv = raw.slice(0, CRYPTO_IV_LEN);
  const data = raw.slice(CRYPTO_IV_LEN);
  const decrypted = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, data);
  return new TextDecoder().decode(decrypted);
}

const WEB_KEY_PREFIX = 'junas_web_api_key_';

function createAppError(code: string, message: string): Error & { code: string } {
  const error = new Error(message) as Error & { code: string };
  error.code = code;
  return error;
}

function normalizeRole(role: string): 'user' | 'assistant' {
  return role === 'assistant' ? 'assistant' : 'user';
}

function clampText(text: string, maxChars: number): string {
  return text.length <= maxChars ? text : `${text.slice(0, maxChars)}\n\n[Truncated output]`;
}

function extractHtmlText(html: string): string {
  if (typeof DOMParser === 'undefined') return html;
  const parsed = new DOMParser().parseFromString(html, 'text/html');
  return parsed.body?.textContent?.replace(/\s+/g, ' ').trim() || '';
}

async function readWebApiKey(provider: string): Promise<string> {
  if (typeof window === 'undefined') {
    throw createAppError('KEYCHAIN_ERROR', 'API key storage is unavailable outside the browser.');
  }
  const stored = localStorage.getItem(`${WEB_KEY_PREFIX}${provider}`);
  if (!stored) return '';
  try {
    return await decryptString(stored);
  } catch {
    return stored; // fallback: legacy unencrypted key
  }
}

async function writeWebApiKey(provider: string, key: string): Promise<void> {
  if (typeof window === 'undefined') {
    throw createAppError('KEYCHAIN_ERROR', 'API key storage is unavailable outside the browser.');
  }
  const encrypted = await encryptString(key);
  localStorage.setItem(`${WEB_KEY_PREFIX}${provider}`, encrypted);
}

function removeWebApiKey(provider: string): void {
  if (typeof window === 'undefined') {
    throw createAppError('KEYCHAIN_ERROR', 'API key storage is unavailable outside the browser.');
  }
  localStorage.removeItem(`${WEB_KEY_PREFIX}${provider}`);
}

async function tauriInvoke<T>(command: string, args: Record<string, unknown>): Promise<T> {
  try {
    const { invoke } = await import('@tauri-apps/api/core');
    return await invoke<T>(command, args);
  } catch (error) {
    throw toErrorWithCode(error);
  }
}

async function invokeWithRuntime<T>(
  command: string,
  args: Record<string, unknown>
): Promise<T> {
  if (!isTauriRuntime()) {
    throw createAppError('UNSUPPORTED_RUNTIME', `Command "${command}" requires Tauri runtime.`);
  }
  return tauriInvoke<T>(command, args);
}

function normalizeOpenAIEndpoint(endpoint: string): string {
  const trimmed = endpoint.replace(/\/+$/, '');
  if (trimmed.endsWith('/v1')) return `${trimmed}/chat/completions`;
  if (trimmed.endsWith('/chat/completions')) return trimmed;
  return `${trimmed}/v1/chat/completions`;
}

function ensureUrl(pathOrUrl: string): string {
  try {
    new URL(pathOrUrl);
    return pathOrUrl;
  } catch {
    throw createAppError('NETWORK_ERROR', `Invalid URL: ${pathOrUrl}`);
  }
}

async function fetchJson<T>(url: string, init: RequestInit): Promise<T> {
  const response = await fetch(ensureUrl(url), init);
  if (!response.ok) {
    const errorBody = await response.text().catch(() => '');
    throw createAppError(
      'PROVIDER_ERROR',
      `Request failed (${response.status} ${response.statusText}): ${errorBody || 'No details'}`
    );
  }
  return (await response.json()) as T;
}

function buildWebChatSettings(settings: ChatSettings): ChatSettings {
  return {
    temperature: settings.temperature ?? 0.7,
    max_tokens: settings.max_tokens ?? 4096,
    top_p: settings.top_p ?? 0.95,
    system_prompt: settings.system_prompt,
  };
}

// --- web streaming infrastructure ---
let webStreamCallback: ((chunk: StreamChunk) => void) | null = null;

function emitWebChunk(delta: string, done: boolean): void {
  webStreamCallback?.({ delta, done });
}

async function readSSEStream(
  response: Response,
  extractDelta: (parsed: Record<string, unknown>) => string | null,
  doneSignal?: string,
): Promise<string> {
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let full = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith(':')) continue;
      if (trimmed === (doneSignal || 'data: [DONE]')) {
        emitWebChunk('', true);
        continue;
      }
      if (!trimmed.startsWith('data: ')) continue;
      try {
        const json = JSON.parse(trimmed.slice(6)) as Record<string, unknown>;
        const delta = extractDelta(json);
        if (delta) {
          full += delta;
          emitWebChunk(delta, false);
        }
      } catch { /* skip malformed json lines */ }
    }
  }
  emitWebChunk('', true);
  return full;
}

async function readNDJSONStream(
  response: Response,
  extractDelta: (parsed: Record<string, unknown>) => string | null,
): Promise<string> {
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let full = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        const json = JSON.parse(line) as Record<string, unknown>;
        const delta = extractDelta(json);
        if (delta) {
          full += delta;
          emitWebChunk(delta, false);
        }
      } catch { /* skip malformed */ }
    }
  }
  emitWebChunk('', true);
  return full;
}

// --- provider web implementations ---
async function chatOpenAiWeb(
  messages: Message[],
  model: string,
  settings: ChatSettings,
  apiKey: string
): Promise<ProviderResponse> {
  const useStream = webStreamCallback !== null;
  const body = {
    model,
    messages: messages.map((m) => ({ role: m.role, content: m.content })),
    temperature: settings.temperature,
    max_tokens: settings.max_tokens,
    top_p: settings.top_p,
    stream: useStream,
  };
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${apiKey}`,
  };
  if (useStream) {
    const response = await fetch(ensureUrl('https://api.openai.com/v1/chat/completions'), {
      method: 'POST', headers, body: JSON.stringify(body),
    });
    if (!response.ok) {
      const err = await response.text().catch(() => '');
      throw createAppError('PROVIDER_ERROR', `OpenAI stream failed (${response.status}): ${err}`);
    }
    const content = await readSSEStream(response, (json) => {
      const choices = json.choices as Array<{ delta?: { content?: string } }> | undefined;
      return choices?.[0]?.delta?.content || null;
    });
    if (!content) throw createAppError('PROVIDER_ERROR', 'OpenAI returned an empty response.');
    return { content, model };
  }
  const result = await fetchJson<OpenAIStyleResponse>('https://api.openai.com/v1/chat/completions', {
    method: 'POST', headers, body: JSON.stringify(body),
  });
  const content = result.choices?.[0]?.message?.content?.trim();
  if (!content) throw createAppError('PROVIDER_ERROR', 'OpenAI returned an empty response.');
  return { content, model, usage: result.usage };
}

interface ClaudeBlock { type: string; text?: string; }
interface ClaudeResponse { content?: ClaudeBlock[]; }

async function chatClaudeWeb(
  messages: Message[],
  model: string,
  settings: ChatSettings,
  apiKey: string
): Promise<ProviderResponse> {
  const useStream = webStreamCallback !== null;
  const body = {
    model,
    max_tokens: settings.max_tokens ?? 4096,
    temperature: settings.temperature ?? 0.7,
    system: settings.system_prompt || undefined,
    stream: useStream,
    messages: messages
      .filter((m) => m.role !== 'system')
      .map((m) => ({ role: normalizeRole(m.role), content: m.content })),
  };
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'x-api-key': apiKey,
    'anthropic-version': '2023-06-01',
    'anthropic-dangerous-direct-browser-access': 'true',
  };
  if (useStream) {
    const response = await fetch(ensureUrl('https://api.anthropic.com/v1/messages'), {
      method: 'POST', headers, body: JSON.stringify(body),
    });
    if (!response.ok) {
      const err = await response.text().catch(() => '');
      throw createAppError('PROVIDER_ERROR', `Claude stream failed (${response.status}): ${err}`);
    }
    const content = await readSSEStream(response, (json) => {
      if (json.type === 'content_block_delta') {
        const delta = json.delta as { text?: string } | undefined;
        return delta?.text || null;
      }
      return null;
    }, 'data: {"type":"message_stop"}');
    if (!content) throw createAppError('PROVIDER_ERROR', 'Claude returned an empty response.');
    return { content, model };
  }
  const result = await fetchJson<ClaudeResponse>('https://api.anthropic.com/v1/messages', {
    method: 'POST', headers, body: JSON.stringify(body),
  });
  const content = (result.content || [])
    .filter((b) => b.type === 'text' && typeof b.text === 'string')
    .map((b) => b.text || '')
    .join('\n')
    .trim();
  if (!content) throw createAppError('PROVIDER_ERROR', 'Claude returned an empty response.');
  return { content, model };
}

interface GeminiPart { text?: string; }
interface GeminiResponse {
  candidates?: Array<{ content?: { parts?: GeminiPart[] } }>;
}

async function chatGeminiWeb(
  messages: Message[],
  model: string,
  settings: ChatSettings,
  apiKey: string
): Promise<ProviderResponse> {
  const useStream = webStreamCallback !== null;
  const body = {
    system_instruction: settings.system_prompt
      ? { parts: [{ text: settings.system_prompt }] }
      : undefined,
    contents: messages
      .filter((m) => m.role !== 'system')
      .map((m) => ({
        role: m.role === 'assistant' ? 'model' : 'user',
        parts: [{ text: m.content }],
      })),
    generationConfig: {
      temperature: settings.temperature ?? 0.7,
      topP: settings.top_p ?? 0.95,
      maxOutputTokens: settings.max_tokens ?? 4096,
    },
  };
  if (useStream) {
    const url = `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:streamGenerateContent?alt=sse&key=${encodeURIComponent(apiKey)}`;
    const response = await fetch(ensureUrl(url), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const err = await response.text().catch(() => '');
      throw createAppError('PROVIDER_ERROR', `Gemini stream failed (${response.status}): ${err}`);
    }
    const content = await readSSEStream(response, (json) => {
      const candidates = json.candidates as Array<{ content?: { parts?: Array<{ text?: string }> } }> | undefined;
      const parts = candidates?.[0]?.content?.parts;
      return parts?.map((p) => p.text || '').join('') || null;
    });
    if (!content) throw createAppError('PROVIDER_ERROR', 'Gemini returned an empty response.');
    return { content, model };
  }
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:generateContent?key=${encodeURIComponent(apiKey)}`;
  const result = await fetchJson<GeminiResponse>(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const parts = result.candidates?.[0]?.content?.parts || [];
  const content = parts.map((p) => p.text || '').join('\n').trim();
  if (!content) throw createAppError('PROVIDER_ERROR', 'Gemini returned an empty response.');
  return { content, model };
}

async function chatOllamaWeb(
  messages: Message[],
  model: string,
  endpoint: string,
  settings: ChatSettings
): Promise<ProviderResponse> {
  const useStream = webStreamCallback !== null;
  const base = endpoint.replace(/\/+$/, '');
  const url = `${base}/api/chat`;
  const payload = {
    model,
    messages,
    stream: useStream,
    options: {
      temperature: settings.temperature ?? 0.7,
      top_p: settings.top_p ?? 0.95,
      num_predict: settings.max_tokens ?? 4096,
    },
  };
  if (useStream) {
    const response = await fetch(ensureUrl(url), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const err = await response.text().catch(() => '');
      throw createAppError('PROVIDER_ERROR', `Ollama stream failed (${response.status}): ${err}`);
    }
    const content = await readNDJSONStream(response, (json) => {
      const msg = json.message as { content?: string } | undefined;
      return msg?.content || null;
    });
    if (!content) throw createAppError('PROVIDER_ERROR', 'Ollama returned an empty response.');
    return { content, model };
  }
  const result = await fetchJson<{ message?: { content?: string } }>(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const content = result.message?.content?.trim();
  if (!content) throw createAppError('PROVIDER_ERROR', 'Ollama returned an empty response.');
  return { content, model };
}

async function chatLmStudioWeb(
  messages: Message[],
  model: string,
  endpoint: string,
  settings: ChatSettings
): Promise<ProviderResponse> {
  const useStream = webStreamCallback !== null;
  const url = normalizeOpenAIEndpoint(endpoint);
  const payload = {
    model,
    messages,
    temperature: settings.temperature ?? 0.7,
    top_p: settings.top_p ?? 0.95,
    max_tokens: settings.max_tokens ?? 4096,
    stream: useStream,
  };
  if (useStream) {
    const response = await fetch(ensureUrl(url), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const err = await response.text().catch(() => '');
      throw createAppError('PROVIDER_ERROR', `LM Studio stream failed (${response.status}): ${err}`);
    }
    const content = await readSSEStream(response, (json) => {
      const choices = json.choices as Array<{ delta?: { content?: string } }> | undefined;
      return choices?.[0]?.delta?.content || null;
    });
    if (!content) throw createAppError('PROVIDER_ERROR', 'LM Studio returned an empty response.');
    return { content, model };
  }
  const result = await fetchJson<OpenAIStyleResponse>(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const content = result.choices?.[0]?.message?.content?.trim();
  if (!content) throw createAppError('PROVIDER_ERROR', 'LM Studio returned an empty response.');
  return { content, model, usage: result.usage };
}

// --- keychain ---
export async function getApiKey(provider: string): Promise<string> {
  if (isTauriRuntime()) return invokeWithRuntime<string>('get_api_key', { provider });
  return readWebApiKey(provider);
}

export async function setApiKey(provider: string, key: string): Promise<void> {
  if (isTauriRuntime()) {
    await invokeWithRuntime<void>('set_api_key', { provider, key });
    return;
  }
  await writeWebApiKey(provider, key);
}

export async function deleteApiKey(provider: string): Promise<void> {
  if (isTauriRuntime()) {
    await invokeWithRuntime<void>('delete_api_key', { provider });
    return;
  }
  removeWebApiKey(provider);
}

// --- chat providers ---
export async function chatClaude(
  messages: Message[], model: string, settings: ChatSettings, apiKey: string
): Promise<ProviderResponse> {
  if (isTauriRuntime()) return invokeWithRuntime<ProviderResponse>('chat_claude', { messages, model, settings: buildWebChatSettings(settings), apiKey });
  return chatClaudeWeb(messages, model, settings, apiKey);
}

export async function chatOpenai(
  messages: Message[], model: string, settings: ChatSettings, apiKey: string
): Promise<ProviderResponse> {
  if (isTauriRuntime()) return invokeWithRuntime<ProviderResponse>('chat_openai', { messages, model, settings: buildWebChatSettings(settings), apiKey });
  return chatOpenAiWeb(messages, model, settings, apiKey);
}

export async function chatGemini(
  messages: Message[], model: string, settings: ChatSettings, apiKey: string
): Promise<ProviderResponse> {
  if (isTauriRuntime()) return invokeWithRuntime<ProviderResponse>('chat_gemini', { messages, model, settings: buildWebChatSettings(settings), apiKey });
  return chatGeminiWeb(messages, model, settings, apiKey);
}

export async function chatOllama(
  messages: Message[], model: string, endpoint: string, settings: ChatSettings
): Promise<ProviderResponse> {
  if (isTauriRuntime()) return invokeWithRuntime<ProviderResponse>('chat_ollama', { messages, model, endpoint, settings: buildWebChatSettings(settings) });
  return chatOllamaWeb(messages, model, endpoint, settings);
}

export async function chatLmstudio(
  messages: Message[], model: string, endpoint: string, settings: ChatSettings
): Promise<ProviderResponse> {
  if (isTauriRuntime()) return invokeWithRuntime<ProviderResponse>('chat_lmstudio', { messages, model, endpoint, settings: buildWebChatSettings(settings) });
  return chatLmStudioWeb(messages, model, endpoint, settings);
}

// --- tools ---
export async function fetchUrl(url: string): Promise<string> {
  if (isTauriRuntime()) return invokeWithRuntime<string>('fetch_url', { url });
  try {
    const response = await fetch(ensureUrl(url), { method: 'GET' });
    if (!response.ok) {
      throw createAppError('NETWORK_ERROR', `Unable to fetch URL (${response.status} ${response.statusText}).`);
    }
    const contentType = response.headers.get('content-type') || '';
    const rawText = await response.text();
    if (contentType.includes('text/html')) return clampText(extractHtmlText(rawText), MAX_FETCH_TEXT_CHARS);
    return clampText(rawText, MAX_FETCH_TEXT_CHARS);
  } catch (error) {
    if (error instanceof Error && 'code' in error) throw error;
    throw toErrorWithCode(error);
  }
}

export async function webSearch(query: string, apiKey: string): Promise<SearchResult[]> {
  if (isTauriRuntime()) return invokeWithRuntime<SearchResult[]>('web_search', { query, apiKey });
  try {
    const response = await fetch('https://google.serper.dev/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-KEY': apiKey },
      body: JSON.stringify({ q: query, num: 8 }),
    });
    if (!response.ok) {
      const body = await response.text().catch(() => '');
      throw createAppError('NETWORK_ERROR', `Serper search failed (${response.status}): ${body || 'No details'}.`);
    }
    const payload = (await response.json()) as { organic?: Array<{ title?: string; link?: string; snippet?: string }> };
    return (payload.organic || [])
      .filter((item) => typeof item.title === 'string' && typeof item.link === 'string')
      .map((item) => ({ title: item.title || 'Untitled Result', url: item.link || '', snippet: item.snippet || '' }));
  } catch (error) {
    if (error instanceof Error && 'code' in error) throw error;
    throw toErrorWithCode(error);
  }
}

// --- health check with real API pings for cloud providers ---
export async function healthCheck(provider: string, endpoint?: string): Promise<boolean> {
  if (isTauriRuntime()) return invokeWithRuntime<boolean>('health_check', { provider, endpoint });
  if (provider === 'ollama') {
    const base = (endpoint || 'http://localhost:11434').replace(/\/+$/, '');
    const r = await fetch(`${base}/api/tags`, { method: 'GET' }).catch(() => null);
    return Boolean(r?.ok);
  }
  if (provider === 'lmstudio') {
    const base = (endpoint || 'http://localhost:1234').replace(/\/+$/, '');
    const r = await fetch(`${base}/v1/models`, { method: 'GET' }).catch(() => null);
    return Boolean(r?.ok);
  }
  const key = await getApiKey(provider).catch(() => '');
  if (!key.trim()) return false;
  try {
    if (provider === 'openai') {
      const r = await fetch('https://api.openai.com/v1/models', {
        method: 'GET',
        headers: { Authorization: `Bearer ${key}` },
        signal: AbortSignal.timeout(8000),
      });
      return r.ok;
    }
    if (provider === 'claude') {
      const r = await fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': key,
          'anthropic-version': '2023-06-01',
          'anthropic-dangerous-direct-browser-access': 'true',
        },
        body: JSON.stringify({ model: 'claude-3-haiku-20240307', max_tokens: 1, messages: [{ role: 'user', content: 'hi' }] }),
        signal: AbortSignal.timeout(8000),
      });
      return r.ok || r.status === 429; // 429 = valid key, rate limited
    }
    if (provider === 'gemini') {
      const r = await fetch(`https://generativelanguage.googleapis.com/v1beta/models?key=${encodeURIComponent(key)}`, {
        method: 'GET',
        signal: AbortSignal.timeout(8000),
      });
      return r.ok;
    }
  } catch { /* network error = unhealthy */ }
  return false;
}

// --- document parsing (browser-side via pdfjs-dist + mammoth) ---
export interface ParsedDocument {
  filename: string;
  text: string;
  page_count: number;
  char_count: number;
}

async function parsePdfInBrowser(file: File): Promise<ParsedDocument> {
  const pdfjs = await import('pdfjs-dist');
  pdfjs.GlobalWorkerOptions.workerSrc = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version}/pdf.worker.min.mjs`;
  const buf = await file.arrayBuffer();
  const doc = await pdfjs.getDocument({ data: new Uint8Array(buf) }).promise;
  const pages: string[] = [];
  for (let i = 1; i <= doc.numPages; i++) {
    const page = await doc.getPage(i);
    const tc = await page.getTextContent();
    pages.push(tc.items.map((item) => ('str' in item ? (item as { str: string }).str : '')).join(' '));
  }
  const text = pages.join('\n\n');
  return { filename: file.name, text, page_count: doc.numPages, char_count: text.length };
}

async function parseDocxInBrowser(file: File): Promise<ParsedDocument> {
  const mammoth = await import('mammoth');
  const buf = await file.arrayBuffer();
  const result = await mammoth.extractRawText({ arrayBuffer: buf });
  const text = result.value;
  return { filename: file.name, text, page_count: 1, char_count: text.length };
}

export async function parsePdf(pathOrFile: string | File): Promise<ParsedDocument> {
  if (!isTauriRuntime()) {
    if (pathOrFile instanceof File) return parsePdfInBrowser(pathOrFile);
    throw createAppError('UNSUPPORTED_RUNTIME', 'Pass a File object for browser PDF parsing.');
  }
  return invokeWithRuntime<ParsedDocument>('parse_pdf', { path: pathOrFile as string });
}

export async function parseDocx(pathOrFile: string | File): Promise<ParsedDocument> {
  if (!isTauriRuntime()) {
    if (pathOrFile instanceof File) return parseDocxInBrowser(pathOrFile);
    throw createAppError('UNSUPPORTED_RUNTIME', 'Pass a File object for browser DOCX parsing.');
  }
  return invokeWithRuntime<ParsedDocument>('parse_docx', { path: pathOrFile as string });
}

// --- streaming ---
export async function onChatStream(callback: (chunk: StreamChunk) => void): Promise<UnlistenFn> {
  if (!isTauriRuntime()) {
    webStreamCallback = callback;
    return () => { webStreamCallback = null; };
  }
  try {
    const { listen } = await import('@tauri-apps/api/event');
    return await listen<StreamChunk>('chat-stream', (event) => callback(event.payload));
  } catch (error) {
    throw toErrorWithCode(error);
  }
}
