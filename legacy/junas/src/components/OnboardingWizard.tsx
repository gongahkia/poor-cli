import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { StorageManager } from '@/lib/storage';
import { COMMANDS } from '@/lib/commands/command-processor';

const STEPS = [
  { id: 'welcome', title: 'Welcome to Junas' },
  { id: 'provider', title: 'Set Up an AI Provider' },
  { id: 'commands', title: 'Explore Slash Commands' },
  { id: 'ready', title: "You're Ready" },
] as const;

interface Props {
  open: boolean;
  onComplete: () => void;
  onOpenConfig: () => void;
}

export function OnboardingWizard({ open, onComplete, onOpenConfig }: Props) {
  const [step, setStep] = useState(0);
  const current = STEPS[step];
  const isLast = step === STEPS.length - 1;
  const handleNext = () => {
    if (isLast) {
      StorageManager.setOnboardingCompleted();
      onComplete();
    } else {
      setStep((s) => s + 1);
    }
  };
  const handleSkip = () => {
    StorageManager.setOnboardingCompleted();
    onComplete();
  };
  const aiCommands = COMMANDS.filter((c) => !c.isLocal && c.implemented);
  const localCommands = COMMANDS.filter((c) => c.isLocal && c.implemented);
  return (
    <Dialog open={open} onOpenChange={() => {}}>
      <DialogContent className="sm:max-w-lg" onPointerDownOutside={(e) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>{current.title}</DialogTitle>
          <DialogDescription>
            Step {step + 1} of {STEPS.length}
          </DialogDescription>
        </DialogHeader>
        <div className="py-4 text-sm leading-relaxed">
          {current.id === 'welcome' && (
            <div className="space-y-3">
              <p>
                Junas is a <strong>BYOK</strong> (Bring Your Own Key) AI legal assistant
                specialized in <strong>Singapore law</strong>.
              </p>
              <p>It helps with contract analysis, case law research, document drafting,
                compliance checking, and due diligence — all from your desktop.</p>
              <p>Your API keys are stored securely in your OS keychain. No data is sent
                to external servers beyond your chosen AI provider.</p>
            </div>
          )}
          {current.id === 'provider' && (
            <div className="space-y-3">
              <p>Junas supports 5 AI providers:</p>
              <ul className="list-disc pl-5 space-y-1">
                <li><strong>Anthropic Claude</strong> — best for nuanced legal reasoning</li>
                <li><strong>OpenAI GPT-4o</strong> — strong general-purpose analysis</li>
                <li><strong>Google Gemini</strong> — fast and capable</li>
                <li><strong>Ollama</strong> — fully local, no API key needed</li>
                <li><strong>LM Studio</strong> — local model server</li>
              </ul>
              <p>You need at least one provider configured to use AI features.</p>
              <Button variant="outline" size="sm" onClick={onOpenConfig}>
                Open Settings to Add API Key
              </Button>
            </div>
          )}
          {current.id === 'commands' && (
            <div className="space-y-3">
              <p>Type <code>/</code> in the chat to access slash commands:</p>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                <div>
                  <p className="font-semibold mb-1">AI-Powered</p>
                  {aiCommands.map((c) => (
                    <p key={c.id} className="text-muted-foreground">/{c.id}</p>
                  ))}
                </div>
                <div>
                  <p className="font-semibold mb-1">Local (No API)</p>
                  {localCommands.map((c) => (
                    <p key={c.id} className="text-muted-foreground">/{c.id}</p>
                  ))}
                </div>
              </div>
              <p className="text-xs text-muted-foreground">
                Open the command palette with <kbd>Cmd+Shift+P</kbd> for quick access.
              </p>
            </div>
          )}
          {current.id === 'ready' && (
            <div className="space-y-3">
              <p>Try these to get started:</p>
              <ul className="list-disc pl-5 space-y-1">
                <li>Ask: <em>"What are the elements of negligence under Singapore law?"</em></li>
                <li>Use <code>/extract-entities</code> to identify parties in legal text</li>
                <li>Use <code>/analyze-contract</code> with contract text for risk analysis</li>
              </ul>
              <p className="text-xs text-muted-foreground">
                You can revisit settings anytime via the gear icon in the sidebar.
              </p>
            </div>
          )}
        </div>
        <DialogFooter className="flex justify-between">
          <Button variant="ghost" size="sm" onClick={handleSkip}>
            Skip
          </Button>
          <div className="flex gap-2">
            {step > 0 && (
              <Button variant="outline" size="sm" onClick={() => setStep((s) => s - 1)}>
                Back
              </Button>
            )}
            <Button size="sm" onClick={handleNext}>
              {isLast ? 'Get Started' : 'Next'}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
