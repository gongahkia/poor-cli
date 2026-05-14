import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { StorageManager } from '@/lib/storage';
import { ChatState, ChatSettings, Conversation } from '@/types/chat';
import { getApiKey } from '@/lib/tauri-bridge';
import { PROVIDER_IDS } from '@/lib/providers/registry';
interface JunasState {
  settings: ChatSettings;
  chatState: ChatState | null;
  conversations: Conversation[];
  configuredProviders: Record<string, boolean>;
  updateSettings: (settings: ChatSettings) => void;
  updateChatState: (state: ChatState) => void;
  saveConversation: (conversation: Conversation) => void;
  deleteConversation: (id: string) => void;
  refreshConfiguredProviders: () => Promise<void>;
}
const JunasContext = createContext<JunasState | undefined>(undefined);
export function JunasProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<ChatSettings>(StorageManager.getSettings());
  const [chatState, setChatState] = useState<ChatState | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [configuredProviders, setConfiguredProviders] = useState<Record<string, boolean>>({});
  const hydrateConversations = async () => {
    try {
      const summaries = await StorageManager.getConversationsAsync();
      const loaded = await Promise.all(
        summaries.map(async (summary) => {
          const conversation = await StorageManager.loadConversationById(summary.id);
          return conversation;
        })
      );

      setConversations(loaded.filter((c): c is Conversation => c !== null));
    } catch {
      setConversations([]);
    }
  };

  useEffect(() => {
    StorageManager.init().then(() => {
      setSettings(StorageManager.getSettings());
      setChatState(StorageManager.getChatState());
      hydrateConversations();
    });
    refreshConfiguredProviders();
  }, []);
  const refreshConfiguredProviders = async () => {
    const configured: Record<string, boolean> = {};
    for (const p of PROVIDER_IDS) {
      try {
        const k = await getApiKey(p);
        configured[p] = !!k;
      } catch {
        configured[p] = false;
      }
    }
    setConfiguredProviders(configured);
  };
  const updateSettings = (newSettings: ChatSettings) => {
    setSettings(newSettings);
    StorageManager.saveSettings(newSettings);
  };
  useEffect(() => {
    if (settings.darkMode) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
    if (settings.theme) {
      document.documentElement.setAttribute('data-theme', settings.theme);
    }
  }, [settings.darkMode, settings.theme]);
  const updateChatState = (newState: ChatState) => {
    setChatState(newState);
    StorageManager.saveChatState(newState);
  };
  const saveConversation = (conversation: Conversation) => {
    StorageManager.saveConversation(conversation);
    setConversations((prev) => {
      const existingIndex = prev.findIndex((item) => item.id === conversation.id);
      if (existingIndex === -1) return [conversation, ...prev];

      const updated = [...prev];
      updated[existingIndex] = conversation;
      return updated;
    });
  };
  const deleteConversation = (id: string) => {
    StorageManager.deleteConversation(id);
    setConversations((prev) => prev.filter((conversation) => conversation.id !== id));
  };
  return (
    <JunasContext.Provider
      value={{
        settings,
        chatState,
        conversations,
        configuredProviders,
        updateSettings,
        updateChatState,
        saveConversation,
        deleteConversation,
        refreshConfiguredProviders,
      }}
    >
      {children}
    </JunasContext.Provider>
  );
}
export function useJunasContext() {
  const context = useContext(JunasContext);
  if (context === undefined) throw new Error('useJunasContext must be used within a JunasProvider');
  return context;
}
