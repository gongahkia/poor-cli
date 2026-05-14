import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Eye, EyeOff, ExternalLink, Check, X } from 'lucide-react';
import { deleteApiKey, getApiKey, setApiKey } from '@/lib/tauri-bridge';

interface ApiKeyModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const providers = [
  {
    id: 'gemini',
    name: 'Google Gemini',
    description: "Google's advanced AI model with strong reasoning capabilities",
    url: 'https://makersuite.google.com/app/apikey',
    placeholder: 'Enter your Gemini API key',
  },
  {
    id: 'openai',
    name: 'OpenAI GPT',
    description: "OpenAI's powerful language models including GPT-4",
    url: 'https://platform.openai.com/api-keys',
    placeholder: 'Enter your OpenAI API key',
  },
  {
    id: 'claude',
    name: 'Anthropic Claude',
    description: "Anthropic's AI assistant with excellent analysis capabilities",
    url: 'https://console.anthropic.com/',
    placeholder: 'Enter your Claude API key',
  },
];

export function ApiKeyModal({ isOpen, onClose }: ApiKeyModalProps) {
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({});
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});
  const [isSaving, setIsSaving] = useState(false);
  const [configured, setConfigured] = useState<Record<string, boolean>>({
    gemini: false,
    openai: false,
    claude: false,
  });

  useEffect(() => {
    if (isOpen) {
      // Load current configuration status from keychain-backed Tauri commands.
      loadConfigStatus();
    } else {
      // Reset visibility state when modal closes
      setShowKeys({});
    }
  }, [isOpen]);

  const loadConfigStatus = async () => {
    const nextConfigured: Record<string, boolean> = {
      gemini: false,
      openai: false,
      claude: false,
    };
    const nextKeys: Record<string, string> = {};

    try {
      for (const provider of providers) {
        try {
          const key = await getApiKey(provider.id);
          if (key?.trim()) {
            nextConfigured[provider.id] = true;
            nextKeys[provider.id] = key;
          }
        } catch {
          nextConfigured[provider.id] = false;
        }
      }

      setConfigured(nextConfigured);
      setApiKeys(nextKeys);
    } catch (error) {
      console.error('Failed to load API key status:', error);
    }
  };

  const handleKeyChange = (provider: string, value: string) => {
    setApiKeys((prev) => ({ ...prev, [provider]: value }));
  };

  const handleToggleVisibility = (provider: string) => {
    setShowKeys((prev) => ({ ...prev, [provider]: !prev[provider] }));
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      for (const provider of providers) {
        const value = apiKeys[provider.id]?.trim() || '';
        if (value) {
          await setApiKey(provider.id, value);
        } else if (configured[provider.id]) {
          await deleteApiKey(provider.id);
        }
      }

      // Clear local state and close
      setApiKeys({});
      await loadConfigStatus();
      onClose();
    } catch (error) {
      console.error('Failed to save API keys:', error);
      alert('Failed to save API keys. Please try again.');
    } finally {
      setIsSaving(false);
    }
  };

  const handleClear = (provider: string) => {
    setApiKeys((prev) => ({ ...prev, [provider]: '' }));
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>API Key Configuration</DialogTitle>
          <DialogDescription>
            Configure your API keys for different AI providers. Your keys are stored securely in
            your OS keychain.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6">
          {providers.map((provider) => (
            <Card key={provider.id}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="text-lg">{provider.name}</CardTitle>
                    <CardDescription>{provider.description}</CardDescription>
                  </div>
                  <div className="flex items-center space-x-2">
                    {(apiKeys[provider.id] && apiKeys[provider.id].trim() !== '') ||
                    configured[provider.id] ? (
                      <div className="flex items-center space-x-1 text-green-600">
                        <Check className="w-4 h-4" />
                        <span className="text-sm">Configured</span>
                      </div>
                    ) : (
                      <div className="flex items-center space-x-1 text-muted-foreground">
                        <X className="w-4 h-4" />
                        <span className="text-sm">Not configured</span>
                      </div>
                    )}
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex space-x-2">
                  <div className="flex-1">
                    <Input
                      type={showKeys[provider.id] ? 'text' : 'password'}
                      placeholder={provider.placeholder}
                      value={apiKeys[provider.id] || ''}
                      onChange={(e) => handleKeyChange(provider.id, e.target.value)}
                    />
                  </div>
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => handleToggleVisibility(provider.id)}
                  >
                    {showKeys[provider.id] ? (
                      <EyeOff className="w-4 h-4" />
                    ) : (
                      <Eye className="w-4 h-4" />
                    )}
                  </Button>
                  {apiKeys[provider.id] && (
                    <Button variant="outline" size="icon" onClick={() => handleClear(provider.id)}>
                      <X className="w-4 h-4" />
                    </Button>
                  )}
                </div>

                <div className="flex items-center space-x-2">
                  <Button
                    variant="link"
                    size="sm"
                    onClick={() => window.open(provider.url, '_blank')}
                    className="p-0 h-auto"
                  >
                    <ExternalLink className="w-4 h-4 mr-1" />
                    Get API key
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        <div className="flex justify-end space-x-2 pt-4 border-t">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={isSaving}>
            {isSaving ? 'Saving...' : 'Save Keys'}
          </Button>
        </div>

        <div className="text-xs text-muted-foreground space-y-1">
          <p>
            <strong>Security:</strong> API keys are stored via Tauri keychain integration and never
            committed to source.
          </p>
          <p>
            <strong>Privacy:</strong> Requests are sent directly from your desktop app to the
            selected provider.
          </p>
          <p>
            <strong>Storage:</strong> Keys are managed in your local OS keychain and can be updated
            anytime.
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
