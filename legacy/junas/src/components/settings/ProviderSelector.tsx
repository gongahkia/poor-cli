import { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Check, X } from 'lucide-react';
import { getApiKey } from '@/lib/tauri-bridge';

interface ProviderSelectorProps {
  currentProvider: string;
  onProviderChange: (provider: string) => void;
}

const providers = [
  {
    id: 'gemini',
    name: 'Google Gemini',
    description: 'Fast and efficient with strong reasoning capabilities',
    features: ['Fast responses', 'Good reasoning', 'Free tier available'],
    hasKey: false,
  },
  {
    id: 'openai',
    name: 'OpenAI GPT',
    description: 'Powerful language model with excellent text generation',
    features: ['High quality responses', 'Code generation', 'Creative writing'],
    hasKey: false,
  },
  {
    id: 'claude',
    name: 'Anthropic Claude',
    description: 'Excellent for analysis and complex reasoning tasks',
    features: ['Strong analysis', 'Long context', 'Ethical AI'],
    hasKey: false,
  },
];

export function ProviderSelector({ currentProvider, onProviderChange }: ProviderSelectorProps) {
  const [configured, setConfigured] = useState<Record<string, boolean>>({
    gemini: false,
    openai: false,
    claude: false,
  });

  useEffect(() => {
    // Load configuration status from keychain-backed Tauri commands.
    loadConfigStatus();
  }, []);

  const loadConfigStatus = async () => {
    const nextConfigured: Record<string, boolean> = {};

    try {
      for (const provider of providers) {
        try {
          const key = await getApiKey(provider.id);
          nextConfigured[provider.id] = Boolean(key?.trim());
        } catch {
          nextConfigured[provider.id] = false;
        }
      }

      setConfigured(nextConfigured);
    } catch (error) {
      console.error('Failed to load API key status:', error);
    }
  };

  const hasApiKey = (provider: string) => {
    return configured[provider];
  };

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold mb-2">AI Provider</h3>
        <p className="text-sm text-muted-foreground">
          Choose your preferred AI provider. You can switch between providers at any time.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {providers.map((provider) => {
          const isSelected = currentProvider === provider.id;
          const hasKey = hasApiKey(provider.id);
          const isAvailable = hasKey;

          return (
            <Card
              key={provider.id}
              className={`cursor-pointer transition-all ${
                isSelected
                  ? 'ring-2 ring-primary border-primary'
                  : isAvailable
                    ? 'hover:border-primary/50'
                    : 'opacity-50 cursor-not-allowed'
              }`}
              onClick={() => isAvailable && onProviderChange(provider.id)}
            >
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">{provider.name}</CardTitle>
                  <div className="flex items-center space-x-1">
                    {isSelected && <Check className="w-4 h-4 text-primary" />}
                    {!hasKey && <X className="w-4 h-4 text-muted-foreground" />}
                  </div>
                </div>
                <CardDescription className="text-sm">{provider.description}</CardDescription>
              </CardHeader>

              <CardContent className="pt-0">
                <div className="space-y-2">
                  <div className="text-xs text-muted-foreground">Features:</div>
                  <ul className="text-xs space-y-1">
                    {provider.features.map((feature, index) => (
                      <li key={index} className="flex items-center space-x-1">
                        <div className="w-1 h-1 bg-muted-foreground rounded-full" />
                        <span>{feature}</span>
                      </li>
                    ))}
                  </ul>

                  <div className="pt-2">
                    {hasKey ? (
                      <div className="flex items-center space-x-1 text-green-600 text-xs">
                        <Check className="w-3 h-3" />
                        <span>API key configured</span>
                      </div>
                    ) : (
                      <div className="flex items-center space-x-1 text-muted-foreground text-xs">
                        <X className="w-3 h-3" />
                        <span>API key required</span>
                      </div>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <div className="text-xs text-muted-foreground">
        <p>
          <strong>Note:</strong> Configure API keys in the API Keys section. Keys are securely
          stored in your OS keychain.
        </p>
      </div>
    </div>
  );
}
