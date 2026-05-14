import { useState, useEffect } from 'react';
import { getModelsWithStatus, AVAILABLE_MODELS } from '@/lib/ml/model-manager';
import { getApiKey, healthCheck } from '@/lib/tauri-bridge';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { ChevronDown, Cpu, Cloud } from 'lucide-react';
import { PROVIDER_LIST } from '@/lib/providers/registry';

interface InlineProviderSelectorProps {
  currentProvider: string;
  onProviderChange: (provider: string) => void;
  disabled?: boolean;
}

export function InlineProviderSelector({
  currentProvider,
  onProviderChange,
  disabled,
}: InlineProviderSelectorProps) {
  const [configuredProviders, setConfiguredProviders] = useState<string[]>([]);
  const [providerHealth, setProviderHealth] = useState<Record<string, string>>({});
  const [hasLocalModels, setHasLocalModels] = useState(false);

  const checkStatus = async () => {
    // Check local models
    const models = await getModelsWithStatus();
    const downloadedCount = models.filter((m) => m.isDownloaded).length;
    setHasLocalModels(downloadedCount === AVAILABLE_MODELS.length);

    // Check provider configuration via keychain
    const configured: string[] = [];
    const health: Record<string, string> = {};

    for (const provider of PROVIDER_LIST) {
      let keyOrEndpoint = '';
      try {
        keyOrEndpoint = await getApiKey(provider.id);
      } catch {
        keyOrEndpoint = '';
      }

      const isConfigured = provider.isLocal
        ? Boolean((keyOrEndpoint || provider.defaultEndpoint)?.trim())
        : Boolean(keyOrEndpoint?.trim());

      if (isConfigured) {
        configured.push(provider.id);
      }

      if (!isConfigured && !provider.isLocal) {
        continue;
      }

      try {
        const endpoint = provider.isLocal ? keyOrEndpoint || provider.defaultEndpoint : undefined;
        const ok = await healthCheck(provider.id, endpoint);
        health[provider.id] = ok ? 'online' : 'offline';
      } catch {
        health[provider.id] = 'offline';
      }
    }

    setConfiguredProviders(configured);
    setProviderHealth(health);
  };

  useEffect(() => {
    checkStatus();

    // Refresh health every 30 seconds
    const interval = setInterval(checkStatus, 30000);

    window.addEventListener('focus', checkStatus);
    return () => {
      clearInterval(interval);
      window.removeEventListener('focus', checkStatus);
    };
  }, []);

  const getProviderLabel = (id: string) => {
    switch (id) {
      case 'local':
        return 'Local Models (Offline)';
      case 'gemini':
        return 'Google Gemini';
      case 'openai':
        return 'OpenAI GPT-4';
      case 'claude':
        return 'Anthropic Claude';
      case 'ollama':
        return 'Ollama (Local)';
      case 'lmstudio':
        return 'LM Studio (Local)';
      default:
        return id.charAt(0).toUpperCase() + id.slice(1);
    }
  };

  const getProviderIcon = (id: string) => {
    if (id === 'local' || id === 'ollama' || id === 'lmstudio') return <Cpu className="h-3 w-3" />;
    return <Cloud className="h-3 w-3" />;
  };

  const getHealthIndicator = (id: string) => {
    if (id === 'local')
      return <div className="h-1.5 w-1.5 rounded-full bg-green-500" title="Available" />;

    const status = providerHealth[id];
    if (status === 'online')
      return <div className="h-1.5 w-1.5 rounded-full bg-green-500" title="Online" />;
    if (status === 'offline')
      return <div className="h-1.5 w-1.5 rounded-full bg-red-500" title="Offline" />;
    return <div className="h-1.5 w-1.5 rounded-full bg-gray-400" title="Unconfigured" />;
  };

  const availableOptions = [...(hasLocalModels ? ['local'] : []), ...configuredProviders];

  if (availableOptions.length === 0) {
    return <span className="text-xs text-muted-foreground">No providers available</span>;
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        disabled={disabled}
        className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50 outline-none"
      >
        <div className="flex items-center gap-1.5">
          {getProviderIcon(currentProvider)}
          <span className="font-mono hidden md:inline">{getProviderLabel(currentProvider)}</span>
        </div>
        <div className="flex items-center gap-1.5 ml-1">
          {getHealthIndicator(currentProvider)}
          <ChevronDown className="h-3 w-3 opacity-50" />
        </div>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-56">
        {availableOptions.map((id) => (
          <DropdownMenuItem
            key={id}
            onClick={() => onProviderChange(id)}
            className="flex items-center gap-2 text-xs font-mono cursor-pointer"
          >
            {getProviderIcon(id)}
            <span className="flex-1">{getProviderLabel(id)}</span>
            <div className="flex items-center gap-2">
              {getHealthIndicator(id)}
              {currentProvider === id && <span className="text-[10px]">✓</span>}
            </div>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
