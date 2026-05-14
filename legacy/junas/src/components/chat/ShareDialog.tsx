import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Message } from '@/types/chat';
import { Link, Copy, Check } from 'lucide-react';
import { compressChat } from '@/lib/share-utils';
import { useToast } from '@/components/ui/toast';

interface ShareDialogProps {
  isOpen: boolean;
  onClose: () => void;
  messages: Message[];
  nodeMap?: Record<string, Message>;
  currentLeafId?: string;
}

export function ShareDialog({ isOpen, onClose, messages, nodeMap, currentLeafId }: ShareDialogProps) {
  const [shareLink, setShareLink] = useState<string>('');
  const [isCopied, setIsCopied] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const { addToast } = useToast();

  const generateLink = () => {
    setIsGenerating(true);
    // Use setTimeout to allow UI update before heavy compression
    setTimeout(() => {
      try {
        const compressed = compressChat({ messages, nodeMap, currentLeafId });
        const url = `${window.location.origin}/share?d=${compressed}`;
        setShareLink(url);
      } catch (error) {
        console.error('Failed to generate link:', error);
        addToast({
          type: 'error',
          title: 'Error',
          description: 'Failed to generate share link. The conversation might be too long.',
        });
      } finally {
        setIsGenerating(false);
      }
    }, 100);
  };

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(shareLink);
      setIsCopied(true);
      addToast({
        type: 'success',
        title: 'Copied',
        description: 'Share link copied to clipboard',
      });
      setTimeout(() => setIsCopied(false), 2000);
    } catch (err) {
      addToast({
        type: 'error',
        title: 'Error',
        description: 'Failed to copy to clipboard',
      });
    }
  };

  const handleOpenChange = (open: boolean) => {
    if (!open) {
      // Reset state when closing
      setShareLink('');
      setIsCopied(false);
    }
    onClose();
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md font-mono">
        <DialogHeader>
          <DialogTitle className="text-sm">
            [ ↗ Share Conversation ]
          </DialogTitle>
          <DialogDescription className="text-xs">
            Generate a unique link to share this conversation with others.
          </DialogDescription>
        </DialogHeader>

        <div className="py-4 space-y-4">
          {!shareLink ? (
            <div className="flex flex-col items-center justify-center py-6 text-center space-y-3">
              <div className="p-3 rounded-full bg-muted">
                <Link className="w-6 h-6 text-muted-foreground" />
              </div>
              <p className="text-sm text-muted-foreground">
                Anyone with the link can view a read-only version of this chat.
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              <label className="text-xs font-medium text-muted-foreground">
                Share Link
              </label>
              <div className="flex items-center gap-2">
                <input
                  readOnly
                  value={shareLink}
                  className="flex-1 px-3 py-2 text-xs bg-muted/50 border rounded-md focus:outline-none focus:ring-1 focus:ring-primary font-mono text-muted-foreground truncate"
                  onClick={(e) => e.currentTarget.select()}
                />
                <button
                  onClick={copyToClipboard}
                  className={`p-2 rounded-md border transition-all ${
                    isCopied
                      ? 'bg-green-500/10 border-green-500/50 text-green-600'
                      : 'hover:bg-muted text-muted-foreground'
                  }`}
                  title="Copy to clipboard"
                >
                  {isCopied ? (
                    <Check className="w-4 h-4" />
                  ) : (
                    <Copy className="w-4 h-4" />
                  )}
                </button>
              </div>
            </div>
          )}
        </div>

        <DialogFooter>
          <button
            onClick={onClose}
            className="px-3 py-2 text-xs hover:bg-muted transition-colors mr-2"
          >
            [ Close ]
          </button>
          {!shareLink && (
            <button
              onClick={generateLink}
              disabled={isGenerating}
              className="px-3 py-2 text-xs hover:bg-muted transition-colors border rounded-sm disabled:opacity-50"
            >
              {isGenerating ? '[ Generating... ]' : '[ Generate Link ]'}
            </button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
