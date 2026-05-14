import { useEffect, useState, useMemo } from 'react';
import { Message } from '@/types/chat';
import { decompressChat } from '@/lib/share-utils';
import { MessageList } from '@/components/chat/MessageList';
import { Button } from '@/components/ui/button';
import { StorageManager } from '@/lib/storage';
import { useToast, ToastProvider } from '@/components/ui/toast';
import { Download } from 'lucide-react';
import { Layout } from '@/components/Layout';
import { getLinearHistory, getBranchSiblings } from '@/lib/chat-tree';

function SharePageContent() {
  const searchParams = useMemo(() => new URLSearchParams(window.location.search), []);
  const [messages, setMessages] = useState<Message[]>([]);
  const [nodeMap, setNodeMap] = useState<Record<string, Message>>({});
  const [currentLeafId, setCurrentLeafId] = useState<string | undefined>(undefined);
  const [isValid, setIsValid] = useState(false);
  const [loading, setLoading] = useState(true);
  const { addToast } = useToast();

  useEffect(() => {
    const data = searchParams.get('d');
    if (data) {
      try {
        const decompressed = decompressChat(data);
        if (decompressed && decompressed.messages && decompressed.messages.length > 0) {
          setMessages(decompressed.messages);
          if (decompressed.nodeMap) setNodeMap(decompressed.nodeMap);
          if (decompressed.currentLeafId) setCurrentLeafId(decompressed.currentLeafId);
          setIsValid(true);
        } else {
          setIsValid(false);
        }
      } catch (e) {
        console.error('Failed to parse share data', e);
        setIsValid(false);
      }
    }
    setLoading(false);
  }, [searchParams]);

  const handleImport = () => {
    if (messages.length > 0) {
      // Confirm if user wants to overwrite if there are existing messages?
      // For simplicity, we'll just save it as the current conversation context.
      // If the user already has a chat, this might be destructive if we just use `saveChatState`.
      // A safer approach: Load these messages into the chat state.

      const currentChat = StorageManager.getChatState();

      if (currentChat && currentChat.messages.length > 0) {
        const confirmed = window.confirm(
          'Importing this chat will replace your current active conversation. Do you want to proceed?'
        );
        if (!confirmed) return;
      }

      StorageManager.saveChatState({
        messages: messages,
        nodeMap: nodeMap,
        currentLeafId: currentLeafId,
        artifacts: [], // Initialize with empty artifacts for imported chat
        isLoading: false,
        currentProvider: currentChat?.currentProvider || 'gemini', // Default or keep existing
        settings: StorageManager.getSettings(), // Keep existing settings
      });

      window.location.href = '/';
      addToast({
        type: 'success',
        title: 'Chat Imported',
        description: 'You can now continue the conversation.',
      });
    }
  };

  const handleCopyMessage = async (content: string) => {
    try {
      await navigator.clipboard.writeText(content);
      addToast({
        type: 'success',
        title: 'Copied',
        description: 'Message copied to clipboard',
      });
    } catch {
      addToast({
        type: 'error',
        title: 'Error',
        description: 'Failed to copy',
      });
    }
  };

  const handleBranchSwitch = (messageId: string, direction: 'prev' | 'next') => {
    if (!nodeMap || Object.keys(nodeMap).length === 0) return;
    const siblings = getBranchSiblings(nodeMap, messageId);
    const currentIndex = siblings.indexOf(messageId);

    let nextId = messageId;
    if (direction === 'prev' && currentIndex > 0) {
      nextId = siblings[currentIndex - 1];
    } else if (direction === 'next' && currentIndex < siblings.length - 1) {
      nextId = siblings[currentIndex + 1];
    }

    if (nextId !== messageId) {
      let leaf = nextId;
      while (true) {
        const node = nodeMap[leaf];
        if (!node?.childrenIds || node.childrenIds.length === 0) break;
        leaf = node.childrenIds[node.childrenIds.length - 1];
      }
      setMessages(getLinearHistory(nodeMap, leaf));
      setCurrentLeafId(leaf);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-muted-foreground font-mono text-sm">[ Loading shared chat... ]</div>
      </div>
    );
  }

  if (!isValid) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen space-y-4 text-center px-4">
        <div className="p-4 rounded-full bg-destructive/10 text-destructive">
          <Download className="w-8 h-8" />
        </div>
        <h1 className="text-xl font-bold font-mono">Invalid or Expired Link</h1>
        <p className="text-muted-foreground max-w-md font-mono text-sm">
          The shared link appears to be invalid or corrupted. Please ask the sender to generate a
          new link.
        </p>
        <Button onClick={() => window.location.href = '/'} variant="outline" className="font-mono text-xs">
          [ Return Home ]
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen bg-background">
      <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur px-4 md:px-8 py-3 flex items-center justify-between">
        <div className="font-mono text-sm font-semibold">[ Shared Conversation ]</div>
        <div className="flex items-center gap-4">
          <button
            onClick={handleImport}
            className="px-2 py-1 text-xs font-mono hover:bg-muted transition-colors text-black"
          >
            [ Import & Continue ]
          </button>
        </div>
      </header>

      <main className="flex-1 overflow-hidden flex flex-col relative">
        <MessageList
          messages={messages}
          nodeMap={nodeMap}
          isLoading={false}
          onCopyMessage={handleCopyMessage}
          onRegenerateMessage={() => {}} // No-op for read-only
          onBranchSwitch={handleBranchSwitch}
        />

        {/* Overlay to indicate read-only state at the bottom */}
        <div className="absolute bottom-0 w-full p-4 bg-gradient-to-t from-background to-transparent pointer-events-none flex justify-center pb-8">
          <div className="px-4 py-2 bg-muted/80 backdrop-blur rounded-full text-xs font-mono text-muted-foreground border shadow-sm pointer-events-auto">
            Read-only mode. Click "Import & Continue" to chat.
          </div>
        </div>
      </main>
    </div>
  );
}

export default function SharePage() {
  return (
    <ToastProvider>
      <SharePageContent />
    </ToastProvider>
  );
}
