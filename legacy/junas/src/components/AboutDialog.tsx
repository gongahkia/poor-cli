import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';

interface AboutDialogProps {
  isOpen: boolean;
  onClose: () => void;
}

export function AboutDialog({ isOpen, onClose }: AboutDialogProps) {
  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-xl font-mono">
        <DialogHeader>
          <DialogTitle>[ About ]</DialogTitle>
          <DialogDescription className="hidden">About Junas</DialogDescription>
        </DialogHeader>

        <div className="space-y-4 pt-4 text-sm text-muted-foreground">
          <p>
            Your AI-powered legal assistant for Singapore law.
          </p>
          <p>
            Junas helps you research case law, analyze contracts, draft legal documents,
            and navigate Singapore's legal framework with ease.
          </p>
          <p className="text-xs opacity-75 pt-4 border-t border-muted-foreground/20">
            [ Bring your own API keys • Privacy-focused • All data stays in your browser ]
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
