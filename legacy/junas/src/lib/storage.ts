import { ChatState, ChatSettings, Conversation } from '@/types/chat';
import * as fs from '@/lib/storage/file-storage';
const DEFAULT_SETTINGS: ChatSettings = {
  temperature: 0.7,
  maxTokens: 4000,
  topP: 0.95,
  topK: 40,
  frequencyPenalty: 0.0,
  presencePenalty: 0.0,
  systemPrompt:
    'You are Junas, a legal AI assistant specialized in Singapore law. Provide accurate, helpful legal information while being clear about limitations.',
  autoSave: true,
  darkMode: false,
  agentMode: false,
  focusMode: false,
  theme: 'vanilla',
  profiles: [],
  activeProfileId: undefined,
  snippets: [],
  asciiLogo: '5',
};
let cachedSettings: ChatSettings | null = null; // in-memory cache for sync access
let cachedChatState: ChatState | null = null;
let cachedConversationsList: Conversation[] = [];
export class StorageManager {
  static getChatState(): ChatState | null {
    return cachedChatState;
  }
  static saveChatState(state: ChatState): void {
    cachedChatState = state;
    fs.saveSettings({ ...cachedSettings, _chatState: state }).catch(console.error);
  }
  static clearChatState(): void {
    cachedChatState = null;
  }
  static getSettings(): ChatSettings {
    return cachedSettings || DEFAULT_SETTINGS;
  }
  static saveSettings(settings: ChatSettings): void {
    cachedSettings = settings;
    fs.saveSettings(settings).catch(console.error);
    if (typeof window !== 'undefined') {
      window.dispatchEvent(
        new CustomEvent('junas-settings-change', {
          detail: { settings },
        })
      );
    }
  }
  static getConversations(): Conversation[] {
    return cachedConversationsList;
  }
  static async getConversationsAsync(): Promise<
    { id: string; title: string; createdAt: string; updatedAt: string }[]
  > {
    const summaries = await fs.listConversations();
    const metadata = await Promise.all(
      summaries.map(async (summary) => {
        const conversation = await this.loadConversationById(summary.id);
        return {
          id: summary.id,
          title: conversation?.title || summary.name || summary.id,
          createdAt: conversation?.createdAt
            ? conversation.createdAt.toISOString()
            : new Date(0).toISOString(),
          updatedAt: conversation?.updatedAt
            ? conversation.updatedAt.toISOString()
            : summary.updatedAt || new Date(0).toISOString(),
        };
      })
    );

    const sorted = metadata.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
    // hydrate sync cache
    const loaded = await Promise.all(sorted.map((m) => this.loadConversationById(m.id)));
    cachedConversationsList = loaded.filter((c): c is Conversation => c !== null);
    return sorted;
  }
  static async loadConversationById(id: string): Promise<Conversation | null> {
    const raw = await fs.loadConversation(id);
    if (!raw || typeof raw !== 'object') return null;

    const conversation = raw as Partial<Conversation> & Record<string, unknown>;
    if (!Array.isArray(conversation.messages)) return null;
    const createdAtValue = conversation.createdAt;
    const updatedAtValue = conversation.updatedAt;

    return {
      ...conversation,
      id: typeof conversation.id === 'string' ? conversation.id : id,
      title:
        typeof conversation.title === 'string' && conversation.title.trim().length > 0
          ? conversation.title
          : id,
      createdAt:
        createdAtValue instanceof Date
          ? createdAtValue
          : createdAtValue
            ? new Date(String(createdAtValue))
            : new Date(),
      updatedAt:
        updatedAtValue instanceof Date
          ? updatedAtValue
          : updatedAtValue
            ? new Date(String(updatedAtValue))
            : new Date(),
      messages: conversation.messages,
      artifacts: Array.isArray(conversation.artifacts) ? conversation.artifacts : [],
    } as Conversation;
  }
  static saveConversation(conversation: Conversation): void {
    const idx = cachedConversationsList.findIndex((c) => c.id === conversation.id);
    if (idx >= 0) cachedConversationsList[idx] = conversation;
    else cachedConversationsList.unshift(conversation);
    fs.saveConversation(conversation.id, {
      ...conversation,
      updatedAt: new Date().toISOString(),
    }).catch(console.error);
  }
  static deleteConversation(id: string): void {
    cachedConversationsList = cachedConversationsList.filter((c) => c.id !== id);
    fs.deleteConversation(id).catch(console.error);
  }
  static clearConversations(): void {
    const ids = cachedConversationsList.map((c) => c.id);
    cachedConversationsList = [];
    for (const id of ids) fs.deleteConversation(id).catch(console.error);
  }
  static clearAllData(): void {
    cachedSettings = null;
    cachedChatState = null;
  }
  static hasSeenDisclaimer(): boolean {
    try {
      return localStorage.getItem('junas_disclaimer_seen') === 'true';
    } catch {
      return false;
    }
  }
  static setDisclaimerSeen(): void {
    try {
      localStorage.setItem('junas_disclaimer_seen', 'true');
    } catch {}
  }
  static hasCompletedOnboarding(): boolean {
    try {
      return localStorage.getItem('junas_onboarding_completed') === 'true';
    } catch {
      return false;
    }
  }
  static setOnboardingCompleted(): void {
    try {
      localStorage.setItem('junas_onboarding_completed', 'true');
    } catch {}
  }
  static exportData(): string {
    return JSON.stringify(
      { settings: this.getSettings(), exportDate: new Date().toISOString() },
      null,
      2
    );
  }
  static importData(jsonData: string): boolean {
    try {
      const data = JSON.parse(jsonData);
      if (data.settings) this.saveSettings(data.settings);
      return true;
    } catch {
      return false;
    }
  }
  static async init(): Promise<void> {
    cachedSettings = await fs.loadSettings(DEFAULT_SETTINGS);
  }
}
