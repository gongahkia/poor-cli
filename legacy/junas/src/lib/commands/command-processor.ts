/**
 * Command processor for slash commands
 * Routes commands to either local NLP services or AI
 */

import {
  CommandType,
  COMMANDS,
  ProcessedCommand,
  LocalCommandResult,
  AsyncLocalCommandResult,
  CommandInfo,
} from './definitions';
import type { LegalSearchResult } from '@/lib/legal-sources';
import {
  createSingaporeLegalSourceAdapter,
  loadSingaporeLegalSourceConfigFromStorage,
} from '@/lib/legal-sources';
import { WINDOW_EVENTS, emitWindowEvent } from '@/lib/events';

export type {
  CommandType,
  ProcessedCommand,
  LocalCommandResult,
  AsyncLocalCommandResult,
  CommandInfo,
};
export { COMMANDS };

const COMMAND_TEXT_LIMITS: Partial<Record<CommandType, number>> = {
  'extract-entities': 120_000,
  'analyze-document': 120_000,
  'summarize-local': 80_000,
  'ner-advanced': 80_000,
  'classify-text': 40_000,
  'fetch-url': 2_000,
  'web-search': 500,
  'search-case-law': 1_000,
  'research-statute': 1_000,
  'generate-document': 200_000,
};
const ONNX_REQUIRED_COMMANDS = new Set<CommandType>([
  'summarize-local',
  'ner-advanced',
  'classify-text',
]);

function getDisabledTools(): Set<string> {
  if (typeof window === 'undefined') return new Set();

  try {
    const raw = localStorage.getItem('junas_disabled_tools');
    if (!raw) return new Set();
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return new Set();
    return new Set(parsed.map((tool) => String(tool)));
  } catch {
    return new Set();
  }
}

export function isCommandDisabled(commandId: string): boolean {
  return getDisabledTools().has(commandId);
}

function createConfiguredSingaporeAdapter() {
  const config = loadSingaporeLegalSourceConfigFromStorage();
  return createSingaporeLegalSourceAdapter(config);
}

function validateCommandTextLength(
  commandType: CommandType,
  args: string
): { ok: true } | { ok: false; message: string } {
  const maxLength = COMMAND_TEXT_LIMITS[commandType];
  if (!maxLength) return { ok: true };

  const inputLength = args.length;
  if (inputLength <= maxLength) return { ok: true };

  return {
    ok: false,
    message: [
      `Input too long for /${commandType}.`,
      `Length: ${inputLength.toLocaleString()} characters (max ${maxLength.toLocaleString()}).`,
      `Please truncate your text and retry.`,
    ].join(' '),
  };
}

async function validateOnnxCapability(commandType: CommandType): Promise<string | null> {
  if (!ONNX_REQUIRED_COMMANDS.has(commandType)) return null;

  const { isOnnxRuntimeAvailable } = await import('@/lib/ml/model-manager');
  const available = await isOnnxRuntimeAvailable();
  if (available) return null;

  return `Command /${commandType} is unavailable because ONNX Runtime is not supported in this environment.`;
}

async function searchCaseLawLocalFirst(query: string): Promise<LegalSearchResult[]> {
  return createConfiguredSingaporeAdapter().searchCaseLaw(query);
}

async function researchStatuteLocalFirst(query: string): Promise<LegalSearchResult[]> {
  return createConfiguredSingaporeAdapter().researchStatute(query);
}

function formatLegalSearchResults(
  header: string,
  query: string,
  results: LegalSearchResult[],
  emptyMessage: string
): string {
  let output = `**${header} for "${query}":**\n\n`;
  if (results.length === 0) {
    output += emptyMessage;
    return output;
  }

  results.forEach((result, index) => {
    output += `${index + 1}. **[${result.title}](${result.url})**\n${result.snippet}\n\n`;
  });

  return output;
}

/**
 * Parse a message to detect if it contains a slash command
 */
export function parseCommand(message: string): ProcessedCommand | null {
  const commandPattern = /^\/([a-z-]+)\s*([\s\S]*)/i;
  const match = message.trim().match(commandPattern);

  if (!match) {
    return null;
  }

  const commandId = match[1].toLowerCase() as CommandType;
  const args = match[2].trim();

  const commandInfo = COMMANDS.find((c) => c.id === commandId);
  if (!commandInfo) {
    return null;
  }

  return {
    command: commandId,
    args,
    isLocal: commandInfo.isLocal,
  };
}

/**
 * Check if a command requires an ONNX model
 */
export function requiresModel(commandType: CommandType): string | null {
  const modelMap: Partial<Record<CommandType, string>> = {
    'summarize-local': 'summarization',
    'ner-advanced': 'ner',
    'classify-text': 'text-classification',
  };
  return modelMap[commandType] || null;
}

/**
 * Process a local command (no AI required)
 */
export function processLocalCommand(command: ProcessedCommand): LocalCommandResult {
  const { command: commandType, args } = command;
  if (isCommandDisabled(commandType)) {
    return {
      success: false,
      content: `Command /${commandType} is disabled in Tools settings.`,
    };
  }

  if (!args || args.trim().length === 0) {
    return {
      success: false,
      content: `Please provide text after the /${commandType} command.\n\nExample:\n\`/${commandType} [your text here]\``,
    };
  }

  const lengthValidation = validateCommandTextLength(commandType, args);
  if (!lengthValidation.ok) {
    return {
      success: false,
      content: lengthValidation.message,
    };
  }

  // Check if this command requires a model
  // Note: We need a way to check model status without importing the whole model-manager if possible
  // But for now, we'll keep the logic simple. The heavy lifting is the processing.
  // Ideally, isModelDownloaded should be lightweight.
  // For synchronous check, we assume the caller handles the model check or we assume it's okay to import simple helpers.
  // Actually, to fully optimize, we would need to dynamically import isModelDownloaded too, but that's async.
  // Since processLocalCommand is synchronous signature in the original code involving synchronous NLP,
  // we have to be careful.

  // Wait, extractEntities and analyzeDocument ARE synchronous.
  // We can't make processLocalCommand async if the caller expects sync for these.
  // But the original code imported them top-level.
  // To optimize, we MUST use CommonJS require or just accept that for THESE specific sync commands, we load the lib.
  // BUT: extractEntities uses `compromise`.
  // If we can't make this async, we can't dynamic import (await import).

  // Let's check how processLocalCommand is used.
  // It's used in ChatInterface: const syncResult = processLocalCommand(toolCommand);
  // If we change it to async, we need to update ChatInterface.
  // ChatInterface awaits `generateResponse` which is async.

  // Strategy:
  // 1. Convert `processLocalCommand` to allow returning a Promise OR make ChatInterface handle it.
  // 2. Actually, better: The synchronous commands (extract-entities, analyze-document) rely on `compromise`.
  //    If we want to lazy load `compromise`, we HAVE to make this async or use require() (which might break in strict ESM/Next.js edge cases, but usually fine in Webpack).

  // Let's assume we can change the signature or use require().
  // `require` is not available in standard ESM.

  // Let's look at ChatInterface again.
  // const syncResult = processLocalCommand(toolCommand);
  // It expects a result immediately.

  // If I proceed with this refactor, I should probably catch the need for async in ChatInterface.
  // However, I can cheat:
  // Since 'extract-entities' and 'analyze-document' are the only sync ones causing wide imports,
  // maybe I can just move them to be async too?
  // The original code had them return `LocalCommandResult` directly.

  // If I change the return type to `LocalCommandResult | Promise<LocalCommandResult>`, I break the interface.

  // Let's check `processAsyncLocalCommand`.
  // It handles the ONNX stuff which IS async.

  // Proposal:
  // Move `extract-entities` and `analyze-document` to `processAsyncLocalCommand`.
  // `processLocalCommand` will then just return "__ASYNC_MODEL_COMMAND__" for them too.
  // This allows ChatInterface to await the result in the async path.
  // This is the cleanest way to lazy load `compromise`.

  switch (commandType) {
    case 'extract-entities':
    case 'analyze-document':
    case 'summarize-local':
    case 'ner-advanced':
    case 'classify-text':
    case 'fetch-url':
    case 'web-search':
      return {
        success: true,
        content: '__ASYNC_MODEL_COMMAND__',
        requiresModel: requiresModel(commandType) || undefined,
      };

    case 'use-template': {
      emitWindowEvent(WINDOW_EVENTS.openTemplates);
      return { success: true, content: 'Opening template library...' };
    }

    case 'redline': {
      emitWindowEvent(WINDOW_EVENTS.openRedline);
      return { success: true, content: 'Opening contract redlining view...' };
    }

    case 'search-case-law':
    case 'research-statute':
    case 'analyze-contract':
    case 'summarize-document':
    case 'draft-clause':
    case 'check-compliance':
    case 'due-diligence-review':
      return {
        success: true,
        content: '__ASYNC_MODEL_COMMAND__',
        requiresModel: requiresModel(commandType) || undefined,
      };

    case 'generate-document': {
      // This is purely string manipulation, can stay sync and lightweight
      // Expected args: JSON string or formatted text
      // Try to parse JSON first
      let title = 'Generated Document';
      let type: 'text' | 'markdown' = 'markdown';
      let content = args;

      try {
        // Try to find JSON-like structure
        const jsonMatch = args.match(/({[\s\S]*})/);
        if (jsonMatch) {
          const parsed = JSON.parse(jsonMatch[1]);
          if (parsed.title) title = parsed.title;
          if (parsed.type) type = parsed.type;
          if (parsed.content) content = parsed.content;
        } else {
          // If not JSON, try to extract title from first line if it starts with #
          const lines = args.split('\n');
          if (lines.length > 0 && lines[0].startsWith('#')) {
            title = lines[0].replace(/^#+\s*/, '').trim();
          }
        }
      } catch (e) {
        // Fallback to using raw args as content
        console.warn('Failed to parse generate-document args as JSON', e);
      }

      return {
        success: true,
        content: `Document "${title}" generated successfully. Check the Artifacts tab.`,
        artifact: {
          title,
          type: type as any,
          content,
        },
      };
    }

    default:
      return {
        success: false,
        content: `Command /${commandType} is not a local command.`,
      };
  }
}

/**
 * Process a local command (async)
 */
export async function processAsyncLocalCommand(
  command: ProcessedCommand,
  onProgress?: (content: string) => void
): Promise<AsyncLocalCommandResult> {
  const { command: commandType, args } = command;
  if (isCommandDisabled(commandType)) {
    return {
      success: false,
      content: `Command /${commandType} is disabled in Tools settings.`,
    };
  }

  const lengthValidation = validateCommandTextLength(commandType, args);
  if (!lengthValidation.ok) {
    return {
      success: false,
      content: lengthValidation.message,
    };
  }

  try {
    const onnxCapabilityError = await validateOnnxCapability(commandType);
    if (onnxCapabilityError) {
      return {
        success: false,
        content: onnxCapabilityError,
      };
    }

    switch (commandType) {
      case 'extract-entities': {
        const { runNlpWorkerTask } = await import('@/lib/nlp/worker-client');
        const content = await runNlpWorkerTask('extract-entities', args, onProgress);
        return {
          success: true,
          content,
        };
      }

      case 'analyze-document': {
        const { runNlpWorkerTask } = await import('@/lib/nlp/worker-client');
        const content = await runNlpWorkerTask('analyze-document', args, onProgress);
        return {
          success: true,
          content,
        };
      }

      case 'summarize-local': {
        const { summarize } = await import('@/lib/ml/model-manager');
        const summary = await summarize(args);
        return {
          success: true,
          content: `**Summary:**\n\n${summary}`,
        };
      }

      case 'ner-advanced': {
        const { extractNamedEntities } = await import('@/lib/ml/model-manager');
        const entities = await extractNamedEntities(args);
        if (entities.length === 0) {
          return {
            success: true,
            content:
              '**Named Entity Recognition (BERT)**\n\nNo entities detected in the provided text.',
          };
        }
        const formatted = entities
          .map(
            (e: any) => `- **${e.word}** (${e.entity}) - confidence: ${(e.score * 100).toFixed(1)}%`
          )
          .join('\n');
        return {
          success: true,
          content: `**Named Entity Recognition (BERT)**\n\nFound ${entities.length} entities:\n\n${formatted}`,
        };
      }

      case 'classify-text': {
        const { classifyText } = await import('@/lib/ml/model-manager');
        const classifications = await classifyText(args);
        const top = classifications[0];
        return {
          success: true,
          content: `**Text Classification**\n\nSentiment: **${top.label}**\nConfidence: ${(top.score * 100).toFixed(1)}%`,
        };
      }

      case 'fetch-url': {
        try {
          const { fetchUrl } = await import('@/lib/tauri-bridge');
          const content = await fetchUrl(args);
          return { success: true, content: `**Fetched Content from ${args}:**\n\n${content}` };
        } catch (e: any) {
          return { success: false, content: `Error fetching URL: ${e.message || String(e)}` };
        }
      }
      case 'web-search': {
        try {
          const { webSearch, getApiKey } = await import('@/lib/tauri-bridge');
          const apiKey = await getApiKey('serper');
          const results = await webSearch(args, apiKey);
          let resultText = `**Web Search Results for "${args}":**\n\n`;
          if (results.length > 0) {
            results.forEach((r: any, i: number) => {
              resultText += `${i + 1}. **[${r.title}](${r.url})**\n${r.snippet}\n\n`;
            });
          } else {
            resultText += 'No results found.';
          }
          return { success: true, content: resultText };
        } catch (e: any) {
          return { success: false, content: `Error searching web: ${e.message || String(e)}` };
        }
      }
      case 'search-case-law': {
        try {
          const results = await searchCaseLawLocalFirst(args);
          return {
            success: true,
            content: formatLegalSearchResults(
              'Case Law Search Results',
              args,
              results,
              'No case law results found.'
            ),
          };
        } catch (e: any) {
          return {
            success: false,
            content: `Error searching case law: ${e.message || String(e)}`,
          };
        }
      }
      case 'research-statute': {
        try {
          const results = await researchStatuteLocalFirst(args);
          return {
            success: true,
            content: formatLegalSearchResults(
              'Statute Research Results',
              args,
              results,
              'No statute results found.'
            ),
          };
        } catch (e: any) {
          return {
            success: false,
            content: `Error researching statute: ${e.message || String(e)}`,
          };
        }
      }
      case 'analyze-contract':
      case 'summarize-document':
      case 'draft-clause':
      case 'check-compliance':
      case 'due-diligence-review': {
        const { AI_COMMAND_PROMPTS } = await import('@/lib/prompts/system-prompts');
        const promptBuilder = AI_COMMAND_PROMPTS[commandType];
        if (!promptBuilder) {
          return { success: false, content: `No prompt template for /${commandType}.` };
        }
        return { success: true, content: promptBuilder(args) };
      }

      default:
        return {
          success: false,
          content: `Command /${commandType} does not support async processing.`,
        };
    }
  } catch (error: any) {
    return {
      success: false,
      content: `Error processing command: ${error.message}`,
    };
  }
}

/**
 * Check if a command should be processed locally
 */
export function isLocalCommand(commandId: string): boolean {
  const command = COMMANDS.find((c) => c.id === commandId);
  return command?.isLocal ?? false;
}

/**
 * Recursively resolve nested commands in a string.
 * Pattern: (/command args)
 * Replaces the pattern with the output of the command.
 */
export async function resolveCommandString(text: string): Promise<string> {
  const commandPattern = /\(\s*\/([\w-]+)(?:\s+([^)]*))?\s*\)/;
  let currentText = text;
  let match = currentText.match(commandPattern);
  let depth = 0;
  const MAX_DEPTH = 5; // Prevent infinite loops

  while (match && depth < MAX_DEPTH) {
    const fullMatch = match[0];
    const commandId = match[1] as CommandType;
    const args = match[2] || '';

    // Process the inner command
    const commandData: ProcessedCommand = {
      command: commandId,
      args: args.trim(),
      isLocal: isLocalCommand(commandId),
    };

    let result = '';

    // Try sync processing first
    const syncResult = processLocalCommand(commandData);

    if (syncResult.content === '__ASYNC_MODEL_COMMAND__') {
      const asyncResult = await processAsyncLocalCommand(commandData);
      result = asyncResult.success ? asyncResult.content : `[Error: ${asyncResult.content}]`;
    } else {
      result = syncResult.success ? syncResult.content : `[Error: ${syncResult.content}]`;
    }

    // Replace the matched pattern with the result
    currentText = currentText.replace(fullMatch, result);

    // Find next match
    match = currentText.match(commandPattern);
    depth++;
  }

  return currentText;
}
