import { useState } from 'react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Plus } from 'lucide-react';

interface NewChatDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
}

export function NewChatDialog({ isOpen, onClose, onConfirm }: NewChatDialogProps) {
  const [isLoading, setIsLoading] = useState(false);

  const handleConfirm = async () => {
    setIsLoading(true);
    try {
      await onConfirm();
      onClose();
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <AlertDialog open={isOpen} onOpenChange={onClose}>
      <AlertDialogContent className="font-mono">
        <AlertDialogHeader>
          <AlertDialogTitle className="text-sm">
            [ Start New Chat ]
          </AlertDialogTitle>
          <AlertDialogDescription className="text-xs">
            This will save your current conversation to history and start a fresh chat session.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <div className="space-y-3 text-xs">
          <div className="bg-muted/30 p-3 border border-muted-foreground/30">
            <div className="font-medium mb-1">
              &gt; Note:
            </div>
            <div className="text-muted-foreground">
              You can access past conversations from the History menu.
            </div>
          </div>
        </div>
        <AlertDialogFooter>
          <button
            onClick={onClose}
            disabled={isLoading}
            className="px-3 py-2 text-xs hover:bg-muted transition-colors disabled:opacity-50"
          >
            [ Cancel ]
          </button>
          <button
            onClick={handleConfirm}
            disabled={isLoading}
            className="px-3 py-2 text-xs bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
          >
            [ {isLoading ? 'Starting...' : 'Start New Chat'} ]
          </button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
