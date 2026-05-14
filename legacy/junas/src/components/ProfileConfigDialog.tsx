import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { StorageManager } from '@/lib/storage';

interface ProfileConfigDialogProps {
  isOpen: boolean;
  onClose: () => void;
}

export function ProfileConfigDialog({ isOpen, onClose }: ProfileConfigDialogProps) {
  const [userRole, setUserRole] = useState('');
  const [userPurpose, setUserPurpose] = useState('');

  useEffect(() => {
    if (isOpen) {
      const settings = StorageManager.getSettings();
      setUserRole(settings.userRole || '');
      setUserPurpose(settings.userPurpose || '');
    }
  }, [isOpen]);

  const handleSave = () => {
    const settings = StorageManager.getSettings();
    StorageManager.saveSettings({
      ...settings,
      userRole,
      userPurpose,
    });
    onClose();
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md font-mono">
        <DialogHeader>
          <DialogTitle className="text-sm">[ ⚙ Configure Profile ]</DialogTitle>
          <DialogDescription className="text-xs">
            Set your role and purpose to help Junas provide more relevant assistance.
            This will be used as context in your conversations.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="userRole" className="text-xs font-mono">
              &gt; Your Role
            </Label>
            <Input
              id="userRole"
              placeholder="e.g., lawyer, law student, legal researcher"
              value={userRole}
              onChange={(e) => setUserRole(e.target.value)}
              className="text-xs font-mono"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="userPurpose" className="text-xs font-mono">
              &gt; Your Purpose
            </Label>
            <Input
              id="userPurpose"
              placeholder="e.g., contract analysis, case law research"
              value={userPurpose}
              onChange={(e) => setUserPurpose(e.target.value)}
              className="text-xs font-mono"
            />
          </div>

          <div className="space-y-2">
            <Label className="text-xs font-mono">
              &gt; What are you using Junas for?
            </Label>
            <p className="text-xs text-muted-foreground pl-1">
              {userRole || '[Your Role]'} using Junas for {userPurpose || '[Your Purpose]'}
            </p>
          </div>
        </div>

        <DialogFooter>
          <button
            onClick={onClose}
            className="px-3 py-2 text-xs hover:bg-muted transition-colors"
          >
            [ Cancel ]
          </button>
          <button
            onClick={handleSave}
            className="px-3 py-2 text-xs bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            [ Save ]
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
