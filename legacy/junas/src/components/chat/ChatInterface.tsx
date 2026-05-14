import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { Message, Artifact, Citation } from '@/types/chat';
import { MessageList } from './MessageList';
import { MessageInput } from './MessageInput';
import { ArtifactsTab } from './ArtifactsTab';
import { LegalDisclaimer } from '@/components/LegalDisclaimer';
import { StorageManager } from '@/lib/storage';
import { ChatService } from '@/lib/ai/chat-service';
import { useToast } from '@/components/ui/toast';
import { generateId } from '@/lib/utils';
import {
  COMMANDS,
  parseCommand,
  processLocalCommand,
  processAsyncLocalCommand,
} from '@/lib/commands/command-processor';
import { ASCII_LOGOS } from '@/lib/ascii-logos';
import {
  getModelsWithStatus,
  generateText,
  AVAILABLE_MODELS,
  isOnnxRuntimeAvailable,
} from '@/lib/ml/model-manager';
import { FileText, MessageSquare, GitGraph } from 'lucide-react';
import { cn } from '@/lib/utils';
import { ConfirmationDialog } from './ConfirmationDialog';
import { TreeView } from './TreeView';
import { estimateTokens, estimateCost } from '@/lib/ai/token-utils';
import {
  createTreeFromLinear,
  addChild,
  getLinearHistory,
  getBranchSiblings,
} from '@/lib/chat-tree';
import { useJunasContext } from '@/lib/context/JunasContext';
import {
  extractSingaporeCitations,
  normalizeExtractedCitations,
  validateCitations,
} from '@/lib/citations';
import type { CitationKind } from '@/lib/citations';
import { recordToolObservability } from '@/lib/observability/chat-observability';

interface ChatInterfaceProps {
  activeTab?: 'chat' | 'artifacts' | 'tree';
  onTabChange?: (tab: 'chat' | 'artifacts' | 'tree') => void;
}

function mapCitationKindToType(kind: CitationKind): Citation['type'] {
  return kind === 'statute_cap' || kind === 'my_statute' ? 'statute' : 'case';
}

function buildCitationUrl(citationText: string): string {
  return `https://www.google.com/search?q=${encodeURIComponent(`${citationText} Singapore`)}`;
}

function deriveCitationConfidence(
  status: NonNullable<Citation['citation_status']>,
  issueCount: number
): number {
  const base =
    status === 'valid'
      ? 0.95
      : status === 'incomplete'
        ? 0.65
        : status === 'malformed'
          ? 0.25
          : 0.5;
  const adjusted = base - issueCount * 0.05;
  return Math.max(0, Math.min(1, adjusted));
}

function buildMessageCitations(content: string): Citation[] {
  const extracted = extractSingaporeCitations(content);
  if (extracted.length === 0) return [];

  const normalized = normalizeExtractedCitations(extracted);
  const validated = validateCitations(normalized);
  const deduped = new Map<string, Citation>();

  validated.forEach((citation, index) => {
    const key = `${citation.kind}:${citation.normalizedText}`;
    if (deduped.has(key)) return;
    deduped.set(key, {
      id: `${citation.kind}-${citation.start}-${citation.end}-${index}`,
      title: citation.normalizedText,
      url: buildCitationUrl(citation.normalizedText),
      type: mapCitationKindToType(citation.kind),
      jurisdiction: 'Singapore',
      year: citation.year,
      citation_status: citation.validationStatus,
      citation_confidence: deriveCitationConfidence(
        citation.validationStatus,
        citation.validationIssues.length
      ),
    });
  });

  return Array.from(deduped.values());
}

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

export function ChatInterface({ activeTab: propActiveTab, onTabChange }: ChatInterfaceProps = {}) {
  // Use centralized state from context
  const {
    settings,
    chatState,
    conversations,
    updateChatState,
    saveConversation,
    configuredProviders,
  } = useJunasContext();

  const [messages, setMessages] = useState<Message[]>([]);
  const [nodeMap, setNodeMap] = useState<Record<string, Message>>({});
  const [currentLeafId, setCurrentLeafId] = useState<string | undefined>(undefined);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [conversationId, setConversationId] = useState<string>(generateId());
  const [conversationTitle, setConversationTitle] = useState<string>('');

  const [localActiveTab, setLocalActiveTab] = useState<'chat' | 'artifacts' | 'tree'>('chat');
  const activeTab = propActiveTab ?? localActiveTab;
  const setActiveTab = onTabChange ?? setLocalActiveTab;

  const [isLoading, setIsLoading] = useState(false);
  const [hasMessages, setHasMessages] = useState(false);
  const [currentProvider, setCurrentProvider] = useState<string>('gemini');
  const [onnxRuntimeAvailable, setOnnxRuntimeAvailable] = useState(true);
  const [hasProfileConfig, setHasProfileConfig] = useState(false);
  const { addToast } = useToast();

  const totalTokens = messages.reduce((acc, msg) => acc + (msg.tokenCount || 0), 0);
  const totalCost = messages.reduce((acc, msg) => acc + (msg.cost || 0), 0);

  const [confirmation, setConfirmation] = useState({
    isOpen: false,
    title: '',
    description: '',
    resolve: undefined as ((value: boolean) => void) | undefined,
  });
  const autosaveTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const generationAbortControllerRef = useRef<AbortController | null>(null);
  const activeGenerationIdRef = useRef<string | null>(null);

  const isGenerationActive = useCallback((generationId: string) => {
    return activeGenerationIdRef.current === generationId;
  }, []);

  const beginGeneration = useCallback(() => {
    if (generationAbortControllerRef.current) {
      generationAbortControllerRef.current.abort();
    }
    const controller = new AbortController();
    const generationId = generateId();
    generationAbortControllerRef.current = controller;
    activeGenerationIdRef.current = generationId;
    setIsLoading(true);
    return { controller, generationId };
  }, []);

  const completeGeneration = useCallback(
    (generationId: string) => {
      if (!isGenerationActive(generationId)) return;
      activeGenerationIdRef.current = null;
      generationAbortControllerRef.current = null;
      setIsLoading(false);
    },
    [isGenerationActive]
  );

  const updateAssistantMessage = useCallback(
    (
      assistantId: string,
      content: string,
      extra: Partial<Pick<Message, 'responseTime' | 'tokenCount' | 'cost'>> = {}
    ) => {
      const citations = buildMessageCitations(content);
      setMessages((prev) =>
        prev.map((msg) => (msg.id === assistantId ? { ...msg, content, citations, ...extra } : msg))
      );
      setNodeMap((prev) => {
        const existing = prev[assistantId];
        if (!existing) return prev;
        return {
          ...prev,
          [assistantId]: {
            ...existing,
            content,
            citations,
            ...extra,
          },
        };
      });
    },
    []
  );

  const requestConfirmation = (title: string, description: string): Promise<boolean> => {
    return new Promise((resolve) => {
      setConfirmation({
        isOpen: true,
        title,
        description,
        resolve,
      });
    });
  };

  const handleConfirmationResult = (result: boolean) => {
    if (confirmation.resolve) {
      confirmation.resolve(result);
    }
    setConfirmation((prev) => ({ ...prev, isOpen: false }));
  };

  // Check if user has configured their profile
  useEffect(() => {
    setHasProfileConfig(!!(settings.userRole || settings.userPurpose));
  }, [messages, settings]);

  useEffect(() => {
    return () => {
      if (generationAbortControllerRef.current) {
        generationAbortControllerRef.current.abort();
      }
    };
  }, []);

  const startupLogo = useMemo(() => {
    if (settings.asciiLogo === 'random') {
      const keys = Object.keys(ASCII_LOGOS);
      const randomKey = keys[Math.floor(Math.random() * keys.length)];
      return ASCII_LOGOS[randomKey];
    }
    return ASCII_LOGOS[settings.asciiLogo || '5'] || ASCII_LOGOS['5'];
  }, [settings.asciiLogo]);
  useEffect(() => {
    let isMounted = true;
    isOnnxRuntimeAvailable().then((available) => {
      if (isMounted) setOnnxRuntimeAvailable(available);
    });
    return () => {
      isMounted = false;
    };
  }, []);

  const supportedToolIds = useMemo(
    () =>
      new Set(
        COMMANDS.filter((command) => onnxRuntimeAvailable || !command.requiresOnnx).map(
          (command) => command.id
        )
      ),
    [onnxRuntimeAvailable]
  );

  // Sync with context chat state on load
  useEffect(() => {
    if (!chatState) return;
    let isMounted = true;

    if (chatState.currentProvider) {
      setCurrentProvider(chatState.currentProvider);
    }
    getModelsWithStatus()
      .then((models) => {
        if (!isMounted) return;
        const downloadedCount = models.filter((m) => m.isDownloaded).length;
        if (downloadedCount === AVAILABLE_MODELS.length) {
          setCurrentProvider('local');
        }
      })
      .catch(() => {
        // Keep provider fallback from chat state if model status check fails.
      });

    if (chatState.messages) {
      if (chatState.nodeMap && chatState.currentLeafId) {
        setNodeMap(chatState.nodeMap);
        setCurrentLeafId(chatState.currentLeafId);
        setMessages(getLinearHistory(chatState.nodeMap, chatState.currentLeafId));
      } else {
        // Migration from linear to tree
        const { nodeMap: newMap, leafId } = createTreeFromLinear(chatState.messages);
        setNodeMap(newMap);
        setCurrentLeafId(leafId);
        setMessages(chatState.messages);
      }
      setHasMessages(chatState.messages.length > 0);
    }
    if (chatState.artifacts) {
      setArtifacts(chatState.artifacts);
    }

    // Find matching conversation in history to set ID/Title
    const matchingConv = conversations.find(
      (c) =>
        c.messages.length === chatState.messages?.length &&
        c.messages[0]?.id === chatState.messages?.[0]?.id
    );

    if (matchingConv) {
      setConversationId(matchingConv.id);
      setConversationTitle(matchingConv.title);
    }

    return () => {
      isMounted = false;
    };
  }, [chatState]); // Only re-run if context chatState changes externally (e.g. history selection)

  // Handle import messages
  useEffect(() => {
    const handler = async (event: any) => {
      const importedMessages = event.detail.messages;

      // Show loading message
      const loadingMessage: Message = {
        id: 'import-loading',
        role: 'system',
        content: 'loading',
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, loadingMessage]);
      setIsLoading(true);

      try {
        // Summarize the conversation
        const summary = await summarizeImportedConversation(importedMessages);

        // Remove loading message and add the summary response
        setMessages((prev) => {
          const filtered = prev.filter((m) => m.id !== 'import-loading');
          return [
            ...filtered,
            {
              id: generateId(),
              role: 'assistant',
              content: summary,
              citations: buildMessageCitations(summary),
              timestamp: new Date(),
            },
          ];
        });

        addToast({
          type: 'success',
          title: 'Imported',
          description: 'Previous conversation has been summarized',
          duration: 3000,
        });
      } catch (error) {
        // Remove loading message on error
        setMessages((prev) => prev.filter((m) => m.id !== 'import-loading'));
        addToast({
          type: 'error',
          title: 'Import Failed',
          description: 'Failed to summarize conversation',
          duration: 3000,
        });
      } finally {
        setIsLoading(false);
      }
    };
    window.addEventListener('junas-import', handler);
    return () => window.removeEventListener('junas-import', handler);
  }, [addToast]);

  const summarizeImportedConversation = async (messages: Message[]): Promise<string> => {
    const conversationText = messages
      .map((msg) => `${msg.role.toUpperCase()}: ${msg.content}`)
      .join('\n\n');

    const summarizationPrompt: Message[] = [
      {
        id: 'user-prompt',
        role: 'user',
        content: `Provide a single sentence (maximum 20 words) summarizing what the following conversation was about:\n\n${conversationText}\n\nReply ONLY with: "You were previously talking about [summary]. Feel free to continue asking about it."`,
        timestamp: new Date(),
      },
    ];

    if (currentProvider === 'local') {
      try {
        const prompt = `Summarize conversation: ${conversationText}`;
        return await generateText(prompt);
      } catch (e) {
        console.error('Local summarization failed', e);
        return 'Conversation imported.';
      }
    }

    const result = await ChatService.sendMessage(
      summarizationPrompt,
      configuredProviders,
      settings,
      undefined,
      currentProvider
    );
    return result.content;
  };

  // Persist active conversation whenever content changes.
  useEffect(() => {
    if (!settings.autoSave || messages.length === 0) return;
    if (autosaveTimeoutRef.current) clearTimeout(autosaveTimeoutRef.current);
    autosaveTimeoutRef.current = setTimeout(() => {
      saveConversation({
        id: conversationId,
        title: conversationTitle || 'Untitled Conversation',
        messages,
        nodeMap,
        currentLeafId,
        artifacts,
        createdAt: new Date(),
        updatedAt: new Date(),
      });
    }, 500);
    return () => {
      if (autosaveTimeoutRef.current) clearTimeout(autosaveTimeoutRef.current);
    };
  }, [
    settings.autoSave,
    messages,
    nodeMap,
    currentLeafId,
    artifacts,
    conversationId,
    conversationTitle,
    saveConversation,
  ]);

  // Generate a title for the conversation after first exchange
  useEffect(() => {
    if (messages.length >= 2 && !conversationTitle && !isLoading) {
      const generateTitle = async () => {
        try {
          const titlePrompt = [
            {
              role: 'user',
              content: `Summarize this conversation start into a 3-5 word title. Reply ONLY with the title text.\n\nUser: ${messages[0].content}\nAssistant: ${messages[1].content}`,
            } as Message,
          ];

          let title = '';
          if (currentProvider === 'local') {
            title = await generateText(`Title for: ${messages[0].content}`);
          } else {
            const result = await ChatService.sendMessage(
              titlePrompt,
              configuredProviders,
              settings,
              undefined,
              currentProvider
            );
            title = result.content.replace(/^["']|["']$/g, '').trim();
          }

          if (title) {
            setConversationTitle(title);
          }
        } catch (e) {
          console.error('Failed to generate title', e);
        }
      };
      generateTitle();
    }
  }, [messages, conversationTitle, isLoading, currentProvider]);

  // AI Processing Loop (ReAct Pattern)
  const generateResponse = useCallback(
    async (
      currentMessages: Message[],
      assistantMessageId: string,
      recursionDepth = 0,
      seenToolCalls: Set<string> = new Set(),
      signal?: AbortSignal,
      generationId?: string
    ) => {
      const shouldAbort = () =>
        !!signal?.aborted ||
        (generationId ? activeGenerationIdRef.current !== generationId : false);
      const throwIfAborted = () => {
        if (shouldAbort()) {
          throw createAbortError();
        }
      };

      throwIfAborted();
      const settings = StorageManager.getSettings();
      const maxDepth = settings.agentMode ? 10 : 3;
      const maxToolCallsPerTurn = settings.agentMode ? 6 : 1;

      if (recursionDepth > maxDepth) {
        return 'Error: Maximum tool recursion depth reached.';
      }

      let aiResponseText = '';
      let pendingChunkBuffer = '';
      let flushInterval: ReturnType<typeof setInterval> | null = null;
      let lastCommittedContent = '';
      const STREAM_FLUSH_INTERVAL_MS = 60;

      const updateMessageContent = (text: string) => {
        if (shouldAbort()) return;
        setMessages((prev) =>
          prev.map((msg) => (msg.id === assistantMessageId ? { ...msg, content: text } : msg))
        );
        setNodeMap((prev) => ({
          ...prev,
          [assistantMessageId]: { ...prev[assistantMessageId], content: text },
        }));
      };

      const flushStreamBuffer = (force = false) => {
        if (shouldAbort()) return;
        if (!pendingChunkBuffer && !force) return;

        if (pendingChunkBuffer) {
          aiResponseText += pendingChunkBuffer;
          pendingChunkBuffer = '';
        }

        if (!force && aiResponseText === lastCommittedContent) return;

        lastCommittedContent = aiResponseText;
        updateMessageContent(aiResponseText);
      };

      try {
        // 1. Get response from Provider (Local or API)
        throwIfAborted();
        if (currentProvider === 'local') {
          let prompt = '';
          if (settings.agentMode) {
            const localToolDescription = onnxRuntimeAvailable
              ? 'web-search (for online info), fetch-url (for websites), extract-entities (for legal names), summarize-local (for summaries)'
              : 'web-search (for online info), fetch-url (for websites), extract-entities (for legal names)';
            prompt = `System: You are Junas, a Singapore legal AI. You can use tools by replying ONLY with COMMAND: tool-id args. Available tools: ${localToolDescription}. If you need to search the web, use COMMAND: web-search query.\n\n`;
          }

          prompt +=
            currentMessages
              .slice(-6)
              .map(
                (m) =>
                  `${m.role === 'user' ? 'User' : m.role === 'system' ? 'System' : 'Assistant'}: ${m.content}`
              )
              .join('\n') + '\nAssistant:';

          aiResponseText = await generateText(prompt);
          throwIfAborted();
          updateMessageContent(aiResponseText);
        } else {
          flushInterval = setInterval(() => flushStreamBuffer(), STREAM_FLUSH_INTERVAL_MS);

          const result = await ChatService.sendMessage(
            currentMessages,
            configuredProviders,
            settings,
            (chunk: string) => {
              if (shouldAbort()) return;
              pendingChunkBuffer += chunk;
            },
            currentProvider,
            { signal }
          );

          flushStreamBuffer(true);
          if (flushInterval) {
            clearInterval(flushInterval);
            flushInterval = null;
          }
          throwIfAborted();
          updateMessageContent(result.content);
          aiResponseText = result.content;
        }

        // 2. Check for Tool Commands
        const commandMatch = aiResponseText.match(/^COMMAND:\s*([a-z-]+)\s*([\s\S]*)/i);

        if (commandMatch) {
          if (seenToolCalls.size >= maxToolCallsPerTurn) {
            const limitMessage = `Error: TOOL_LIMIT_EXCEEDED (max_tool_calls_per_turn=${maxToolCallsPerTurn}).`;
            updateMessageContent(limitMessage);
            return limitMessage;
          }

          const commandId = commandMatch[1].toLowerCase() as any;
          const args = commandMatch[2].trim();
          if (!supportedToolIds.has(commandId)) {
            const unsupportedMessage = `Error: Unsupported tool command "${commandId}".`;
            updateMessageContent(unsupportedMessage);
            return unsupportedMessage;
          }
          const commandSignature = `${commandId}:${args}`;

          if (seenToolCalls.has(commandSignature)) {
            const loopMessage = `Error: Tool loop detected for "${commandId}" with identical arguments.`;
            updateMessageContent(loopMessage);
            return loopMessage;
          }
          const nextSeenToolCalls = new Set(seenToolCalls);
          nextSeenToolCalls.add(commandSignature);

          // Check for destructive commands requiring confirmation
          if (['generate-document', 'write-file', 'delete-file'].includes(commandId)) {
            const approved = await requestConfirmation(
              'Execute Tool?',
              `The AI wants to run '${commandId}'. This action might modify or create files.`
            );

            if (!approved) {
              const updatedMessages = [
                ...currentMessages,
                { role: 'assistant', content: aiResponseText } as Message,
                {
                  role: 'system',
                  content: `Tool Execution Denied: User cancelled execution of ${commandId}.`,
                } as Message,
              ];
              return await generateResponse(
                updatedMessages,
                assistantMessageId,
                recursionDepth + 1,
                nextSeenToolCalls,
                signal,
                generationId
              );
            }
          }

          const toolCommand = { command: commandId, args, isLocal: true };
          const toolStartedAt = Date.now();

          updateMessageContent(`[Executing tool: ${commandId}...]`);

          let toolResultContent = '';
          let toolSucceeded = false;
          const syncResult = processLocalCommand(toolCommand);

          if (syncResult.success && syncResult.artifact) {
            const newArtifact: Artifact = {
              id: generateId(),
              ...syncResult.artifact,
              createdAt: Date.now(),
              messageId: assistantMessageId,
            };
            setArtifacts((prev) => [newArtifact, ...prev]);
            addToast({
              title: 'Artifact Generated',
              description: `Created ${newArtifact.title}`,
            });
          }

          if (syncResult.content === '__ASYNC_MODEL_COMMAND__') {
            const asyncResult = await processAsyncLocalCommand(toolCommand, (partialContent) => {
              updateMessageContent(partialContent);
            });
            toolSucceeded = asyncResult.success;
            toolResultContent = asyncResult.success
              ? asyncResult.content
              : `Tool Error: ${asyncResult.content}`;
          } else {
            toolSucceeded = syncResult.success;
            toolResultContent = syncResult.success
              ? syncResult.content
              : `Tool Error: ${syncResult.content}`;
          }
          recordToolObservability(
            commandId,
            Date.now() - toolStartedAt,
            toolSucceeded,
            toolSucceeded ? undefined : toolResultContent
          );

          // 3. Feed result back to AI
          const updatedMessages = [
            ...currentMessages,
            { role: 'assistant', content: aiResponseText } as Message,
            {
              role: 'system',
              content: `Tool Output for ${commandId}:\n${toolResultContent}\n\nBased on this output, provide the final answer to the user.`,
            } as Message,
          ];

          return await generateResponse(
            updatedMessages,
            assistantMessageId,
            recursionDepth + 1,
            nextSeenToolCalls,
            signal,
            generationId
          );
        }

        return aiResponseText;
      } catch (error: unknown) {
        console.error('AI Processing Error:', error);
        throw error;
      } finally {
        if (flushInterval) {
          clearInterval(flushInterval);
        }
      }
    },
    [currentProvider, addToast, supportedToolIds, onnxRuntimeAvailable]
  );

  const handleSendMessage = useCallback(
    async (content: string) => {
      if (!content.trim()) return;
      const { controller: turnController, generationId } = beginGeneration();

      // Resolve chained commands (e.g. /summarize (/fetch-url ...))
      // We do this before determining if it is a command or simple message
      // Note: importing resolveCommandString dynamically to ensure no circular deps if any,
      // although it is imported at top level in my plan, but let's be safe or just use the one from imports if I added it.
      // I need to add import to the top of file too.
      let parsedCommand: ReturnType<typeof parseCommand> | null = null;
      try {
        const { resolveCommandString } = await import('@/lib/commands/command-processor');
        const resolvedContent = await resolveCommandString(content);
        // Check if this is a local command (legacy direct command)
        parsedCommand = parseCommand(resolvedContent);
      } catch (error) {
        if (!isAbortError(error) && isGenerationActive(generationId)) {
          addToast({
            type: 'error',
            title: 'Command Resolution Failed',
            description: error instanceof Error ? error.message : String(error),
            duration: 3000,
          });
        }
        completeGeneration(generationId);
        return;
      }

      // For user message display, don't add context prefix to local commands
      let displayContent = content;
      let enrichedContent = content;

      // Add user context pre-prompt to the first message (only for AI commands)
      if (messages.length === 0 && (!parsedCommand || !parsedCommand.isLocal)) {
        const settings = StorageManager.getSettings();
        if (settings.userRole || settings.userPurpose) {
          const contextParts = [];
          if (settings.userRole) contextParts.push(`a ${settings.userRole}`);
          if (settings.userPurpose) contextParts.push(`using Junas for ${settings.userPurpose}`);
          const contextPrompt = `[Context: I am ${contextParts.join(' ')}]\n\n`;
          enrichedContent = contextPrompt + content;
        }
      }

      const userMessage: Message = {
        id: generateId(),
        role: 'user',
        content: parsedCommand?.isLocal ? displayContent : enrichedContent,
        timestamp: new Date(),
        tokenCount: estimateTokens(parsedCommand?.isLocal ? displayContent : enrichedContent),
        cost: estimateCost(
          estimateTokens(parsedCommand?.isLocal ? displayContent : enrichedContent),
          currentProvider,
          '',
          'input'
        ),
        parentId: currentLeafId,
      };

      // Update tree
      const afterUserMap = addChild(nodeMap, currentLeafId || '', userMessage);
      setNodeMap(afterUserMap);
      setCurrentLeafId(userMessage.id);
      setMessages((prev) => [...prev, userMessage]);

      const startTime = Date.now();

      // Create assistant message
      const assistantMessage: Message = {
        id: generateId(),
        role: 'assistant',
        content: '',
        timestamp: new Date(),
        parentId: userMessage.id,
      };

      // Update tree with assistant
      const afterAssistantMap = addChild(afterUserMap, userMessage.id, assistantMessage);
      setNodeMap(afterAssistantMap);
      setCurrentLeafId(assistantMessage.id);
      setMessages((prev) => [...prev, assistantMessage]);

      // Legacy Local Command Handling
      if (parsedCommand && parsedCommand.isLocal) {
        const localToolStartedAt = Date.now();
        const result = processLocalCommand(parsedCommand);

        // Handle artifact generation
        if (result.success && result.artifact) {
          const newArtifact: Artifact = {
            id: generateId(),
            ...result.artifact,
            createdAt: Date.now(),
            messageId: assistantMessage.id,
          };
          setArtifacts((prev) => [newArtifact, ...prev]);
          addToast({
            title: 'Artifact Generated',
            description: `Created ${newArtifact.title}`,
          });
          setActiveTab('artifacts'); // Switch to artifacts tab
        }

        if (!result.success && result.requiresModel) {
          recordToolObservability(
            parsedCommand.command,
            Date.now() - localToolStartedAt,
            false,
            result.content
          );
          const responseTime = Date.now() - startTime;
          if (isGenerationActive(generationId)) {
            updateAssistantMessage(assistantMessage.id, result.content, { responseTime });
          }
          completeGeneration(generationId);
          return;
        }

        if (result.content === '__ASYNC_MODEL_COMMAND__') {
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMessage.id && isGenerationActive(generationId)
                ? { ...msg, content: 'Loading model and processing...' }
                : msg
            )
          );

          try {
            const asyncResult = await processAsyncLocalCommand(parsedCommand, (partialContent) => {
              if (!isGenerationActive(generationId)) return;
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMessage.id ? { ...msg, content: partialContent } : msg
                )
              );
              setNodeMap((prev) => ({
                ...prev,
                [assistantMessage.id]: { ...prev[assistantMessage.id], content: partialContent },
              }));
            });
            const responseTime = Date.now() - startTime;
            if (isGenerationActive(generationId)) {
              updateAssistantMessage(assistantMessage.id, asyncResult.content, { responseTime });
            }
            recordToolObservability(
              parsedCommand.command,
              Date.now() - localToolStartedAt,
              asyncResult.success,
              asyncResult.success ? undefined : asyncResult.content
            );
          } catch (error: unknown) {
            if (isAbortError(error)) {
              completeGeneration(generationId);
              return;
            }
            const errorMessage = error instanceof Error ? error.message : String(error);
            recordToolObservability(
              parsedCommand.command,
              Date.now() - localToolStartedAt,
              false,
              errorMessage
            );
            const responseTime = Date.now() - startTime;
            if (isGenerationActive(generationId)) {
              updateAssistantMessage(
                assistantMessage.id,
                `Error processing command: ${errorMessage}`,
                {
                  responseTime,
                }
              );
            }
          }
          completeGeneration(generationId);
          return;
        }

        const responseTime = Date.now() - startTime;
        if (isGenerationActive(generationId)) {
          updateAssistantMessage(assistantMessage.id, result.content, { responseTime });
        }
        recordToolObservability(
          parsedCommand.command,
          Date.now() - localToolStartedAt,
          result.success,
          result.success ? undefined : result.content
        );
        completeGeneration(generationId);
        return;
      }

      try {
        const allMessages = [...messages, userMessage];
        const finalResponse = await generateResponse(
          allMessages,
          assistantMessage.id,
          0,
          new Set(),
          turnController.signal,
          generationId
        );

        const responseTime = Date.now() - startTime;
        const tokens = estimateTokens(finalResponse);
        const cost = estimateCost(tokens, currentProvider, '', 'output');

        if (isGenerationActive(generationId)) {
          updateAssistantMessage(assistantMessage.id, finalResponse, {
            responseTime,
            tokenCount: tokens,
            cost,
          });
        }
      } catch (error: unknown) {
        if (isAbortError(error)) return;
        const errorMessage = error instanceof Error ? error.message : String(error);
        if (isGenerationActive(generationId)) {
          updateAssistantMessage(assistantMessage.id, `Error: ${errorMessage}`);
        }
      } finally {
        completeGeneration(generationId);
      }
    },
    [
      messages,
      generateResponse,
      addToast,
      setActiveTab,
      updateAssistantMessage,
      beginGeneration,
      isGenerationActive,
      completeGeneration,
    ]
  );

  const handleRegenerateMessage = useCallback(
    async (messageId: string) => {
      const messageIndex = messages.findIndex((m) => m.id === messageId);
      if (messageIndex === -1) return;
      const msgToRegenerate = messages[messageIndex];

      // We can only regenerate assistant messages
      if (msgToRegenerate.role !== 'assistant') return;

      // Get context up to this message (excluding the message itself)
      const contextMessages = messages.slice(0, messageIndex);
      const parentId = msgToRegenerate.parentId;
      const { controller: turnController, generationId } = beginGeneration();

      // Reset state to this point
      // Create new assistant message placeholder (sibling)
      const newAssistantMessage: Message = {
        id: generateId(),
        role: 'assistant',
        content: '',
        timestamp: new Date(),
        parentId: parentId,
      };

      // Update tree: Add new sibling and switch branch
      const afterRegenMap = addChild(nodeMap, parentId || '', newAssistantMessage);
      setNodeMap(afterRegenMap);
      setCurrentLeafId(newAssistantMessage.id);

      // Update messages: Keep context + new placeholder
      setMessages([...contextMessages, newAssistantMessage]);

      const startTime = Date.now();

      try {
        const finalResponse = await generateResponse(
          contextMessages,
          newAssistantMessage.id,
          0,
          new Set(),
          turnController.signal,
          generationId
        );

        const responseTime = Date.now() - startTime;
        const tokens = estimateTokens(finalResponse);
        const cost = estimateCost(tokens, currentProvider, '', 'output');

        if (isGenerationActive(generationId)) {
          updateAssistantMessage(newAssistantMessage.id, finalResponse, {
            responseTime,
            tokenCount: tokens,
            cost,
          });
        }
      } catch (error: unknown) {
        if (isAbortError(error)) return;
        const errorMessage = error instanceof Error ? error.message : String(error);
        if (isGenerationActive(generationId)) {
          updateAssistantMessage(newAssistantMessage.id, `Error: ${errorMessage}`);
        }
      } finally {
        completeGeneration(generationId);
      }
    },
    [
      messages,
      generateResponse,
      nodeMap,
      currentProvider,
      updateAssistantMessage,
      beginGeneration,
      isGenerationActive,
      completeGeneration,
    ]
  );

  const handleEditMessage = useCallback(
    async (messageId: string, newContent: string) => {
      const originalMessage = nodeMap[messageId];
      if (!originalMessage) return;
      const { controller: turnController, generationId } = beginGeneration();

      const parentId = originalMessage.parentId;

      // Create new sibling
      const newMessage: Message = {
        ...originalMessage,
        id: generateId(),
        content: newContent,
        timestamp: new Date(),
        tokenCount: estimateTokens(newContent),
        cost: estimateCost(estimateTokens(newContent), currentProvider, '', 'input'),
      };

      // Update tree
      const nextNodeMap = addChild(nodeMap, parentId || '', newMessage);
      setNodeMap(nextNodeMap);
      setCurrentLeafId(newMessage.id);

      // Calculate context for AI
      const history = getLinearHistory(nextNodeMap, newMessage.id);
      setMessages(history);
      const startTime = Date.now();

      // Create assistant placeholder
      const assistantMessage: Message = {
        id: generateId(),
        role: 'assistant',
        content: '',
        timestamp: new Date(),
        parentId: newMessage.id,
      };

      const afterAssistantMap = addChild(nextNodeMap, newMessage.id, assistantMessage);
      setNodeMap(afterAssistantMap);
      setCurrentLeafId(assistantMessage.id);
      setMessages([...history, assistantMessage]);

      try {
        const finalResponse = await generateResponse(
          history,
          assistantMessage.id,
          0,
          new Set(),
          turnController.signal,
          generationId
        );
        const responseTime = Date.now() - startTime;
        const tokens = estimateTokens(finalResponse);
        const cost = estimateCost(tokens, currentProvider, '', 'output');

        const finalAssistant = {
          ...assistantMessage,
          content: finalResponse,
          citations: buildMessageCitations(finalResponse),
          responseTime,
          tokenCount: tokens,
          cost,
        };

        if (isGenerationActive(generationId)) {
          setMessages((prev) =>
            prev.map((m) => (m.id === assistantMessage.id ? finalAssistant : m))
          );
          setNodeMap((prev) => ({ ...prev, [assistantMessage.id]: finalAssistant }));
        }
      } catch (e: unknown) {
        if (isAbortError(e)) return;
        const errorMessage = e instanceof Error ? e.message : String(e);
        if (isGenerationActive(generationId)) {
          updateAssistantMessage(assistantMessage.id, `Error: ${errorMessage}`);
        }
      } finally {
        completeGeneration(generationId);
      }
    },
    [
      nodeMap,
      currentProvider,
      generateResponse,
      updateAssistantMessage,
      beginGeneration,
      isGenerationActive,
      completeGeneration,
    ]
  );

  const handleBranchSwitch = useCallback(
    (messageId: string, direction: 'prev' | 'next') => {
      const siblings = getBranchSiblings(nodeMap, messageId);
      const currentIndex = siblings.indexOf(messageId);

      let nextId = messageId;
      if (direction === 'prev' && currentIndex > 0) {
        nextId = siblings[currentIndex - 1];
      } else if (direction === 'next' && currentIndex < siblings.length - 1) {
        nextId = siblings[currentIndex + 1];
      }

      if (nextId !== messageId) {
        // Find the latest leaf for this branch
        let leaf = nextId;
        while (true) {
          const node = nodeMap[leaf];
          if (!node?.childrenIds || node.childrenIds.length === 0) break;
          leaf = node.childrenIds[node.childrenIds.length - 1];
        }

        setCurrentLeafId(leaf);
        setMessages(getLinearHistory(nodeMap, leaf));
      }
    },
    [nodeMap]
  );

  const handleSelectNode = useCallback(
    (nodeId: string) => {
      if (nodeMap[nodeId]) {
        setCurrentLeafId(nodeId);
        setMessages(getLinearHistory(nodeMap, nodeId));
        setActiveTab('chat');
      }
    },
    [nodeMap, setActiveTab]
  );

  const handlePromptSelect = useCallback(
    (prompt: string) => {
      handleSendMessage(prompt);
    },
    [handleSendMessage]
  );

  const copyTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const handleCopyMessage = useCallback(
    async (content: string) => {
      // Prevent multiple rapid copy toasts
      if (copyTimeoutRef.current) {
        return;
      }

      const copyToClipboard = async (text: string): Promise<boolean> => {
        // Try modern clipboard API
        try {
          if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
            await navigator.clipboard.writeText(text);
            return true;
          }
        } catch {
          return false;
        }
        return false;
      };

      const success = await copyToClipboard(content);

      if (success) {
        addToast({
          type: 'success',
          title: 'Copied',
          description: 'Message copied to clipboard',
          duration: 2000,
        });

        // Set a timeout to prevent multiple toasts within 2 seconds
        copyTimeoutRef.current = setTimeout(() => {
          copyTimeoutRef.current = null;
        }, 2000);
      } else {
        addToast({
          type: 'error',
          title: 'Copy failed',
          description: 'Unable to copy to clipboard',
          duration: 2000,
        });
      }
    },
    [addToast]
  );

  return (
    <div className="flex flex-col h-full w-full">
      {/* Tab Header */}
      <div className="shrink-0 border-b">
        <div className="max-w-7xl mx-auto px-4 md:px-8 h-10 flex items-center gap-6 overflow-x-auto no-scrollbar font-mono text-xs">
          <button
            onClick={() => setActiveTab('chat')}
            className={cn(
              'flex items-center gap-2 hover:bg-muted/50 transition-colors px-2 py-1',
              activeTab === 'chat' ? 'font-bold' : 'text-muted-foreground hover:text-foreground'
            )}
          >
            [ Chat ]
          </button>

          <button
            onClick={() => setActiveTab('artifacts')}
            className={cn(
              'flex items-center gap-2 hover:bg-muted/50 transition-colors px-2 py-1',
              activeTab === 'artifacts'
                ? 'font-bold'
                : 'text-muted-foreground hover:text-foreground'
            )}
          >
            [ Artifacts ]
            {artifacts.length > 0 && (
              <span className="text-[10px] opacity-70">({artifacts.length})</span>
            )}
          </button>

          <button
            onClick={() => setActiveTab('tree')}
            className={cn(
              'flex items-center gap-2 hover:bg-muted/50 transition-colors px-2 py-1',
              activeTab === 'tree' ? 'font-bold' : 'text-muted-foreground hover:text-foreground'
            )}
          >
            [ Tree ]
          </button>

          {totalTokens > 0 && (
            <div className="ml-auto hidden md:flex items-center gap-3 text-[10px] text-muted-foreground font-mono">
              <span>{totalTokens.toLocaleString()} tokens</span>
              {totalCost > 0 && <span>${totalCost.toFixed(4)}</span>}
            </div>
          )}
        </div>
      </div>

      {/* Messages area */}
      <div className="flex-1 overflow-hidden relative">
        <div className={cn('h-full flex flex-col', activeTab === 'chat' ? 'flex' : 'hidden')}>
          {messages.length === 0 ? (
            <div className="flex items-center justify-center h-full px-4 py-8">
              <div className="text-center max-w-2xl w-full">
                <div className="overflow-x-auto my-8">
                  <pre className="text-muted-foreground text-xs md:text-sm font-mono leading-tight inline-block">
                    {startupLogo.split('\n').map((line, i) => (
                      <div
                        key={i}
                        className="animate-chunk-jiggle"
                        style={{ animationDelay: `${i * 0.15}s` }}
                      >
                        {line}
                      </div>
                    ))}
                  </pre>
                </div>
                <p className="text-xs text-muted-foreground font-mono mt-6">v2.0.0</p>
              </div>
            </div>
          ) : (
            <MessageList
              messages={messages}
              nodeMap={nodeMap}
              isLoading={isLoading}
              onCopyMessage={handleCopyMessage}
              onRegenerateMessage={handleRegenerateMessage}
              onEditMessage={handleEditMessage}
              onBranchSwitch={handleBranchSwitch}
            />
          )}
        </div>

        <div className={cn('h-full bg-background', activeTab === 'artifacts' ? 'block' : 'hidden')}>
          <ArtifactsTab artifacts={artifacts} />
        </div>

        <div className={cn('h-full bg-background', activeTab === 'tree' ? 'block' : 'hidden')}>
          <TreeView
            nodeMap={nodeMap}
            currentLeafId={currentLeafId}
            onSelectNode={handleSelectNode}
          />
        </div>
      </div>

      {/* Input area */}
      <div
        className={cn(
          'transition-all duration-200',
          activeTab === 'artifacts' || activeTab === 'tree'
            ? 'opacity-50 pointer-events-none'
            : 'opacity-100'
        )}
      >
        <MessageInput
          onSendMessage={handleSendMessage}
          isLoading={isLoading}
          currentProvider={currentProvider}
          onProviderChange={setCurrentProvider}
        />
      </div>

      {/* Legal Disclaimer Overlay */}
      <LegalDisclaimer />

      {/* Confirmation Dialog */}
      <ConfirmationDialog
        isOpen={confirmation.isOpen}
        title={confirmation.title}
        description={confirmation.description}
        onConfirm={() => handleConfirmationResult(true)}
        onCancel={() => handleConfirmationResult(false)}
      />
    </div>
  );
}
