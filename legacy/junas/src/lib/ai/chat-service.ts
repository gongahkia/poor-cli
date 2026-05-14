import { Message, ChatSettings } from '@/types/chat';
import { AIProvider } from '@/types/provider';
import { getDefaultPromptConfig, generateSystemPrompt } from '@/lib/prompts/system-prompts';
import * as bridge from '@/lib/tauri-bridge';
import { getApiKey } from '@/lib/tauri-bridge';
import { getProviderRegistryEntry, PROVIDER_IDS } from '@/lib/providers/registry';
import { estimateTokens } from '@/lib/ai/token-utils';
import { recordProviderObservability } from '@/lib/observability/chat-observability';
import {
  extractSingaporeCitations,
  normalizeExtractedCitations,
  validateCitations,
} from '@/lib/citations';

export interface SendMessageResult {
  content: string;
}

export interface SendMessageOptions {
  signal?: AbortSignal;
}

const LEGAL_ANALYSIS_KEYWORDS = [
  'legal',
  'law',
  'case',
  'case law',
  'statute',
  'act',
  'regulation',
  'court',
  'judgment',
  'citation',
  'negligence',
  'liability',
  'contract',
  'tort',
  'precedent',
  'compliance',
];

const LEGAL_ACCURACY_CAUTION_BLOCK =
  '\n\n**Legal Accuracy Notice:** No valid legal citations were detected in this answer. Verify with authoritative Singapore legal sources before relying on this analysis.';

const PROVIDER_CONTEXT_TOKEN_BUDGET: Partial<Record<AIProvider, number>> = {
  openai: 16_000,
  claude: 18_000,
  gemini: 20_000,
  ollama: 8_000,
  lmstudio: 8_000,
};
const DEFAULT_CONTEXT_TOKEN_BUDGET = 12_000;
const MESSAGE_TOKEN_OVERHEAD = 10;
const MIN_CONTEXT_TOKEN_BUDGET = 1_500;
const CHECKPOINT_MAX_ENTRIES = 12;
const CHECKPOINT_ENTRY_MAX_CHARS = 220;

function createAbortError(): Error {
  const error = new Error('Request cancelled by user.');
  error.name = 'AbortError';
  return error;
}

function isAbortError(error: unknown): boolean {
  const hasDomAbort =
    typeof DOMException !== 'undefined' &&
    error instanceof DOMException &&
    error.name === 'AbortError';
  const hasErrorAbort = error instanceof Error && error.name === 'AbortError';
  return hasDomAbort || hasErrorAbort;
}

function throwIfAborted(signal?: AbortSignal): void {
  if (signal?.aborted) {
    throw createAbortError();
  }
}

async function withAbortSignal<T>(operation: Promise<T>, signal?: AbortSignal): Promise<T> {
  if (!signal) return operation;
  throwIfAborted(signal);

  let abortHandler: (() => void) | null = null;
  const abortPromise = new Promise<never>((_, reject) => {
    abortHandler = () => reject(createAbortError());
    signal.addEventListener('abort', abortHandler, { once: true });
  });

  try {
    return await Promise.race([operation, abortPromise]);
  } finally {
    if (abortHandler) {
      signal.removeEventListener('abort', abortHandler);
    }
  }
}

function isLikelyLegalAnalysisPrompt(messages: Message[]): boolean {
  const lastUserMessage = [...messages].reverse().find((message) => message.role === 'user');
  if (!lastUserMessage) return false;

  const lowered = lastUserMessage.content.toLowerCase();
  return LEGAL_ANALYSIS_KEYWORDS.some((keyword) => lowered.includes(keyword));
}

function hasValidCitation(content: string): boolean {
  const extracted = extractSingaporeCitations(content);
  if (extracted.length === 0) return false;

  const normalized = normalizeExtractedCitations(extracted);
  const validated = validateCitations(normalized);
  return validated.some((citation) => citation.validationStatus === 'valid');
}

function applyLegalAccuracyCaution(messages: Message[], content: string): string {
  if (!isLikelyLegalAnalysisPrompt(messages)) return content;
  if (hasValidCitation(content)) return content;
  if (content.includes('Legal Accuracy Notice:')) return content;
  return `${content}${LEGAL_ACCURACY_CAUTION_BLOCK}`;
}

function resolveContextBudget(provider: string, settings: ChatSettings): number {
  const providerBudget =
    PROVIDER_CONTEXT_TOKEN_BUDGET[provider as AIProvider] || DEFAULT_CONTEXT_TOKEN_BUDGET;
  const requestedOutputTokens = settings.maxTokens ?? 4096;
  const reservedOutputBudget = Math.max(512, Math.min(requestedOutputTokens, 4096));
  return Math.max(MIN_CONTEXT_TOKEN_BUDGET, providerBudget - reservedOutputBudget);
}

function estimateMessageTokens(message: Message): number {
  return MESSAGE_TOKEN_OVERHEAD + estimateTokens(message.content || '');
}

function normalizeCheckpointText(text: string): string {
  return text.replace(/\s+/g, ' ').trim();
}

function truncateCheckpointText(text: string, maxChars: number): string {
  if (text.length <= maxChars) return text;
  return `${text.slice(0, maxChars - 3)}...`;
}

function buildHistoryCheckpointMessage(
  droppedMessages: Message[],
  droppedTokenEstimate: number
): Message | null {
  const candidateEntries = droppedMessages
    .filter((message) => message.role === 'user' || message.role === 'assistant')
    .slice(-CHECKPOINT_MAX_ENTRIES)
    .map((message) => {
      const summary = truncateCheckpointText(
        normalizeCheckpointText(message.content || ''),
        CHECKPOINT_ENTRY_MAX_CHARS
      );
      return `- ${message.role.toUpperCase()}: ${summary || '[empty]'}`;
    });

  if (candidateEntries.length === 0) return null;

  const checkpointBody = [
    `Conversation checkpoint: ${droppedMessages.length} older messages (~${droppedTokenEstimate} tokens) were compacted.`,
    'Key earlier context:',
    ...candidateEntries,
  ].join('\n');

  return {
    id: 'history-checkpoint',
    role: 'system',
    content: checkpointBody,
    timestamp: new Date(0),
  };
}

function pruneMessagesToTokenBudget(messages: Message[], tokenBudget: number): Message[] {
  if (messages.length === 0) return [];

  const kept: Message[] = [];
  const dropped: Message[] = [];
  let usedTokens = 0;
  let droppedTokenEstimate = 0;

  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    const messageTokens = estimateMessageTokens(message);
    const canFit = usedTokens + messageTokens <= tokenBudget;

    if (!canFit && kept.length > 0) {
      dropped.push(message);
      droppedTokenEstimate += messageTokens;
      continue;
    }

    kept.unshift(message);
    usedTokens += messageTokens;
  }

  if (kept.length === 0) {
    return [messages[messages.length - 1]];
  }

  let checkpointMessage = buildHistoryCheckpointMessage(dropped, droppedTokenEstimate);
  while (checkpointMessage && kept.length > 1) {
    const checkpointTokens = estimateMessageTokens(checkpointMessage);
    if (usedTokens + checkpointTokens <= tokenBudget) break;

    const removed = kept.shift();
    if (!removed) break;
    usedTokens -= estimateMessageTokens(removed);
    dropped.push(removed);
    droppedTokenEstimate += estimateMessageTokens(removed);
    checkpointMessage = buildHistoryCheckpointMessage(dropped, droppedTokenEstimate);
  }

  if (checkpointMessage) {
    const checkpointTokens = estimateMessageTokens(checkpointMessage);
    if (usedTokens + checkpointTokens <= tokenBudget) {
      kept.unshift(checkpointMessage);
    }
  }

  return kept;
}

export class ChatService {
  private static getAvailableProvider(configuredProviders: Record<string, boolean>): string | null {
    for (const provider of PROVIDER_IDS) {
      if (configuredProviders[provider]) return provider;
    }
    return null;
  }
  static async sendMessage(
    messages: Message[],
    configuredProviders: Record<string, boolean>,
    settings: ChatSettings,
    onChunk?: (chunk: string) => void,
    preferredProvider?: string,
    options?: SendMessageOptions
  ): Promise<SendMessageResult> {
    try {
      const signal = options?.signal;
      throwIfAborted(signal);

      let provider: string | null = preferredProvider || null;
      if (!provider || !configuredProviders[provider]) {
        provider = this.getAvailableProvider(configuredProviders);
      }
      if (!provider) throw new Error('No API keys configured. Please add an API key in settings.');
      const contextBudget = resolveContextBudget(provider, settings);
      const budgetedMessages = pruneMessagesToTokenBudget(messages, contextBudget);
      const model = getProviderRegistryEntry(provider as AIProvider).defaultModel;
      const config = getDefaultPromptConfig('standard');
      config.useTools = settings.agentMode;
      if (!config.currentDate) {
        config.currentDate = new Date().toLocaleDateString('en-SG', {
          weekday: 'long',
          year: 'numeric',
          month: 'long',
          day: 'numeric',
        });
      }
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      let activeProfile: any = null;
      if (settings.activeProfileId && settings.profiles) {
        activeProfile = settings.profiles.find((p) => p.id === settings.activeProfileId);
      }
      const role = activeProfile?.userRole || settings.userRole;
      const purpose = activeProfile?.userPurpose || settings.userPurpose;
      const customSystemPrompt = activeProfile?.systemPrompt || settings.systemPrompt;
      if (role || purpose) {
        config.userContext = { role: role || undefined, preferences: purpose || undefined };
      }
      if (customSystemPrompt) config.baseSystemPrompt = customSystemPrompt;
      // inject jurisdiction-specific prompt additions
      try {
        const { getJurisdiction, getDefaultJurisdiction } = await import('@/lib/jurisdictions');
        const jurisdictionId = (settings as any).jurisdiction || 'sg';
        const jurisdiction = getJurisdiction(jurisdictionId) || getDefaultJurisdiction();
        if (jurisdiction.systemPromptAddition) {
          config.baseSystemPrompt = (config.baseSystemPrompt || '') + '\n\n' + jurisdiction.systemPromptAddition;
        }
      } catch { /* jurisdictions module unavailable, skip */ }
      config.systemPrompt = generateSystemPrompt(config);
      // RAG context injection: retrieve relevant chunks from indexed documents
      try {
        const { queryRelevantChunks, formatRagContext, listCollections } = await import('@/lib/rag/rag-service');
        const collections = await listCollections();
        if (collections.length > 0) {
          const lastUserMsg = [...messages].reverse().find((m) => m.role === 'user');
          if (lastUserMsg) {
            const allResults = await Promise.all(
              collections.map((col) => queryRelevantChunks(col, lastUserMsg.content, 3))
            );
            const merged = allResults.flat().sort((a, b) => b.score - a.score).slice(0, 5);
            const ragContext = formatRagContext(merged.filter((r) => r.score > 0.3));
            if (ragContext) {
              config.systemPrompt = ragContext + config.systemPrompt;
            }
          }
        }
      } catch { /* RAG unavailable (embeddings model not downloaded), skip silently */ }
      const formattedMessages: bridge.Message[] = budgetedMessages.map((msg) => ({
        role: msg.role,
        content: msg.content,
      }));
      const chatSettings: bridge.ChatSettings = {
        temperature: 0.7,
        max_tokens: 4096,
        system_prompt: config.systemPrompt,
      };
      let unlisten: (() => void) | null = null;
      let removeAbortListener: (() => void) | null = null;
      let fullResponse = '';
      const providerStartTime = Date.now();
      if (onChunk) {
        unlisten = await bridge.onChatStream((chunk) => {
          if (signal?.aborted) return;
          if (!chunk.done && chunk.delta) {
            fullResponse += chunk.delta;
            onChunk(chunk.delta);
          }
        });
      }
      if (signal) {
        const handleAbort = () => {
          if (unlisten) {
            unlisten();
            unlisten = null;
          }
        };
        signal.addEventListener('abort', handleAbort, { once: true });
        removeAbortListener = () => signal.removeEventListener('abort', handleAbort);
      }
      try {
        const executeProviderRequest = async (): Promise<bridge.ProviderResponse> => {
          throwIfAborted(signal);
          if (provider === 'claude') {
            const apiKey = await getApiKey('claude');
            return bridge.chatClaude(formattedMessages, model, chatSettings, apiKey);
          }
          if (provider === 'openai') {
            const apiKey = await getApiKey('openai');
            return bridge.chatOpenai(formattedMessages, model, chatSettings, apiKey);
          }
          if (provider === 'gemini') {
            const apiKey = await getApiKey('gemini');
            return bridge.chatGemini(formattedMessages, model, chatSettings, apiKey);
          }
          if (provider === 'ollama') {
            const storedEndpoint = await getApiKey('ollama').catch(() => '');
            const endpoint = storedEndpoint.trim() || 'http://localhost:11434';
            return bridge.chatOllama(formattedMessages, model, endpoint, chatSettings);
          }
          if (provider === 'lmstudio') {
            const storedEndpoint = await getApiKey('lmstudio').catch(() => '');
            const endpoint = storedEndpoint.trim() || 'http://localhost:1234';
            return bridge.chatLmstudio(formattedMessages, model, endpoint, chatSettings);
          }
          throw new Error(`Unsupported provider: ${provider}`);
        };

        let result: bridge.ProviderResponse;
        try {
          result = await withAbortSignal(executeProviderRequest(), signal);
        } catch (providerError: unknown) {
          recordProviderObservability(
            provider,
            'chat_completion',
            Date.now() - providerStartTime,
            false,
            providerError instanceof Error ? providerError.message : String(providerError)
          );
          throw providerError;
        }

        throwIfAborted(signal);
        recordProviderObservability(
          provider,
          'chat_completion',
          Date.now() - providerStartTime,
          true
        );
        fullResponse = result.content;
      } finally {
        if (removeAbortListener) removeAbortListener();
        if (unlisten) unlisten();
      }
      return { content: applyLegalAccuracyCaution(messages, fullResponse) };
    } catch (error: any) {
      if (isAbortError(error)) throw error;
      if (!error.message?.includes('No API keys configured'))
        console.error('Chat service error:', error);
      if (error && typeof error === 'object' && typeof error.code === 'string') {
        throw error;
      }
      throw new Error(error.message || 'Failed to get AI response');
    }
  }
}
