import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ChatState, Conversation, Message } from '@/types/chat';

const files = new Map<string, unknown>();
const streamController = vi.hoisted(() => ({
  handler: null as ((chunk: { delta: string; done: boolean }) => void) | null,
}));

vi.mock('@/lib/storage/file-storage', () => ({
  saveConversation: vi.fn(async (id: string, data: unknown) => {
    files.set(`conversation:${id}`, data);
  }),
  loadConversation: vi.fn(async (id: string) => files.get(`conversation:${id}`) ?? null),
  listConversations: vi.fn(async () => {
    return Array.from(files.entries())
      .filter(([key]) => key.startsWith('conversation:'))
      .map(([key, value]) => {
        const id = key.replace('conversation:', '');
        const conversation = value as { title?: string; updatedAt?: string };
        return {
          id,
          name: conversation.title || id,
          updatedAt: conversation.updatedAt || '',
        };
      });
  }),
  deleteConversation: vi.fn(async (id: string) => {
    files.delete(`conversation:${id}`);
  }),
  saveSettings: vi.fn(async (settings: unknown) => {
    files.set('settings', settings);
  }),
  loadSettings: vi.fn(async (defaults: unknown) => {
    return (files.get('settings') as unknown) || defaults;
  }),
  saveProfiles: vi.fn(async () => {}),
  loadProfiles: vi.fn(async (defaults: unknown) => defaults),
  saveSnippets: vi.fn(async () => {}),
  loadSnippets: vi.fn(async (defaults: unknown) => defaults),
  saveErrorEvents: vi.fn(async () => {}),
  loadErrorEvents: vi.fn(async (defaults: unknown) => defaults),
}));

vi.mock('@/lib/tauri-bridge', () => ({
  getApiKey: vi.fn(async () => 'test-api-key'),
  onChatStream: vi.fn(async (callback: (chunk: { delta: string; done: boolean }) => void) => {
    streamController.handler = callback;
    return () => {
      streamController.handler = null;
    };
  }),
  chatGemini: vi.fn(async () => {
    streamController.handler?.({ delta: 'Hello ', done: false });
    streamController.handler?.({ delta: 'from smoke test.', done: false });
    streamController.handler?.({ delta: '', done: true });
    return {
      content: 'Hello from smoke test.',
      model: 'gemini-2.0-flash-exp',
    };
  }),
  chatClaude: vi.fn(async () => {
    throw new Error('not used');
  }),
  chatOpenai: vi.fn(async () => {
    throw new Error('not used');
  }),
  chatOllama: vi.fn(async () => {
    throw new Error('not used');
  }),
  chatLmstudio: vi.fn(async () => {
    throw new Error('not used');
  }),
  fetchUrl: vi.fn(async () => ''),
  webSearch: vi.fn(async () => []),
  healthCheck: vi.fn(async () => true),
}));

import { ChatService } from '@/lib/ai/chat-service';
import { StorageManager } from '@/lib/storage';

describe('chat flow smoke test', () => {
  beforeEach(async () => {
    files.clear();
    streamController.handler = null;
    await StorageManager.init();
  });

  it('streams a response, persists chat state, and reloads conversation history', async () => {
    const promptMessage: Message = {
      id: 'msg-user-1',
      role: 'user',
      content: 'Hello there',
      timestamp: new Date(),
    };

    const streamedChunks: string[] = [];
    const response = await ChatService.sendMessage(
      [promptMessage],
      { gemini: true },
      StorageManager.getSettings(),
      (chunk) => streamedChunks.push(chunk),
      'gemini'
    );

    expect(streamedChunks.join('')).toBe('Hello from smoke test.');
    expect(response.content).toContain('Hello from smoke test.');

    const chatState: ChatState = {
      messages: [promptMessage],
      artifacts: [],
      isLoading: false,
      currentProvider: 'gemini',
      settings: StorageManager.getSettings(),
    };
    StorageManager.saveChatState(chatState);
    expect(StorageManager.getChatState()?.messages[0].content).toBe('Hello there');

    const conversation: Conversation = {
      id: 'conv-smoke',
      title: 'Smoke Conversation',
      messages: [
        promptMessage,
        {
          id: 'msg-assistant-1',
          role: 'assistant',
          content: response.content,
          timestamp: new Date(),
        },
      ],
      artifacts: [],
      createdAt: new Date('2026-02-28T10:00:00.000Z'),
      updatedAt: new Date('2026-02-28T10:05:00.000Z'),
    };
    StorageManager.saveConversation(conversation);

    const reloaded = await StorageManager.loadConversationById('conv-smoke');
    expect(reloaded?.messages).toHaveLength(2);
    expect(reloaded?.messages[1].content).toContain('Hello from smoke test.');

    const history = await StorageManager.getConversationsAsync();
    expect(history.some((entry) => entry.id === 'conv-smoke')).toBe(true);
  });
});
