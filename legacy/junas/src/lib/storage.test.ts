import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Conversation } from '@/types/chat';

const mockFs = vi.hoisted(() => ({
  saveConversation: vi.fn(() => Promise.resolve()),
  loadConversation: vi.fn(),
  listConversations: vi.fn(),
  deleteConversation: vi.fn(() => Promise.resolve()),
  saveSettings: vi.fn(() => Promise.resolve()),
  loadSettings: vi.fn(async (defaults: unknown) => defaults),
}));

vi.mock('@/lib/storage/file-storage', () => ({
  saveConversation: mockFs.saveConversation,
  loadConversation: mockFs.loadConversation,
  listConversations: mockFs.listConversations,
  deleteConversation: mockFs.deleteConversation,
  saveSettings: mockFs.saveSettings,
  loadSettings: mockFs.loadSettings,
  saveProfiles: vi.fn(() => Promise.resolve()),
  loadProfiles: vi.fn(async (defaults: unknown) => defaults),
  saveSnippets: vi.fn(() => Promise.resolve()),
  loadSnippets: vi.fn(async (defaults: unknown) => defaults),
}));

import { StorageManager } from '@/lib/storage';

describe('StorageManager conversation persistence', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('loads and normalizes a persisted conversation by id', async () => {
    mockFs.loadConversation.mockResolvedValue({
      id: 'conv-1',
      title: 'Litigation Prep',
      messages: [{ id: 'm1', role: 'user', content: 'test' }],
      createdAt: '2026-02-28T00:00:00.000Z',
      updatedAt: '2026-02-28T01:00:00.000Z',
    });

    const loaded = await StorageManager.loadConversationById('conv-1');

    expect(loaded?.id).toBe('conv-1');
    expect(loaded?.title).toBe('Litigation Prep');
    expect(loaded?.messages).toHaveLength(1);
    expect(loaded?.createdAt).toBeInstanceOf(Date);
    expect(loaded?.updatedAt).toBeInstanceOf(Date);
  });

  it('returns conversation metadata with title and timestamps', async () => {
    mockFs.listConversations.mockResolvedValue([
      { id: 'conv-1', name: 'fallback', updatedAt: '2026-02-28T05:00:00.000Z' },
    ]);
    mockFs.loadConversation.mockResolvedValue({
      id: 'conv-1',
      title: 'Case Law Research',
      messages: [{ id: 'm1', role: 'user', content: 'test' }],
      createdAt: '2026-02-28T03:00:00.000Z',
      updatedAt: '2026-02-28T04:00:00.000Z',
    });

    const metadata = await StorageManager.getConversationsAsync();

    expect(metadata).toEqual([
      {
        id: 'conv-1',
        title: 'Case Law Research',
        createdAt: '2026-02-28T03:00:00.000Z',
        updatedAt: '2026-02-28T04:00:00.000Z',
      },
    ]);
  });

  it('writes conversation snapshots back to storage', () => {
    const conversation: Conversation = {
      id: 'conv-2',
      title: 'Compliance Check',
      messages: [{ id: 'm1', role: 'user', content: 'hello', timestamp: new Date() }],
      artifacts: [],
      createdAt: new Date('2026-02-28T00:00:00.000Z'),
      updatedAt: new Date('2026-02-28T00:00:00.000Z'),
    };

    StorageManager.saveConversation(conversation);

    expect(mockFs.saveConversation).toHaveBeenCalledWith(
      'conv-2',
      expect.objectContaining({
        id: 'conv-2',
        title: 'Compliance Check',
        updatedAt: expect.any(String),
      })
    );
  });

  it('sorts conversation history by latest update timestamp', async () => {
    mockFs.listConversations.mockResolvedValue([
      { id: 'conv-older', name: 'Older', updatedAt: '2026-02-28T01:00:00.000Z' },
      { id: 'conv-newer', name: 'Newer', updatedAt: '2026-02-28T02:00:00.000Z' },
    ]);
    mockFs.loadConversation
      .mockResolvedValueOnce({
        id: 'conv-older',
        title: 'Older',
        messages: [{ id: 'm1', role: 'user', content: 'older' }],
        createdAt: '2026-02-28T00:00:00.000Z',
        updatedAt: '2026-02-28T01:00:00.000Z',
      })
      .mockResolvedValueOnce({
        id: 'conv-newer',
        title: 'Newer',
        messages: [{ id: 'm1', role: 'user', content: 'newer' }],
        createdAt: '2026-02-28T00:00:00.000Z',
        updatedAt: '2026-02-28T02:00:00.000Z',
      });

    const metadata = await StorageManager.getConversationsAsync();

    expect(metadata.map((item) => item.id)).toEqual(['conv-newer', 'conv-older']);
  });
});
