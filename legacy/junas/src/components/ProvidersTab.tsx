import { useState, useEffect } from 'react';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ExternalLink } from 'lucide-react';
import { useJunasContext } from '@/lib/context/JunasContext';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Info } from 'lucide-react';
import { getApiKey, setApiKey, healthCheck } from '@/lib/tauri-bridge';
import { PROVIDER_LIST } from '@/lib/providers/registry';
import { isTauriRuntime } from '@/lib/runtime';
export function ProvidersTab() {
  const [apiKeys, setApiKeysState] = useState<Record<string, string>>({});
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});
  const [isSaving, setIsSaving] = useState(false);
  const [configuredProviders, setConfiguredProviders] = useState<Record<string, boolean>>({});
  const [providerHealth, setProviderHealth] = useState<Record<string, string>>({});
  const runtimeMode = isTauriRuntime() ? 'tauri' : 'web';
  useEffect(() => {
    loadKeys();
    checkAllHealth();
  }, []);
  const loadKeys = async () => {
    const configured: Record<string, boolean> = {};
    const keys: Record<string, string> = {};
    for (const p of PROVIDER_LIST) {
      try {
        const key = await getApiKey(p.id);
        if (key) {
          configured[p.id] = true;
          keys[p.id] = key;
        }
      } catch {
        configured[p.id] = false;
      }
    }
    setConfiguredProviders(configured);
    setApiKeysState(keys);
  };
  const checkAllHealth = async () => {
    const health: Record<string, string> = {};
    for (const p of PROVIDER_LIST) {
      try {
        const ok = await healthCheck(p.id, p.isLocal ? apiKeys[p.id] : undefined);
        health[p.id] = ok ? 'online' : 'offline';
      } catch {
        health[p.id] = 'offline';
      }
    }
    setProviderHealth(health);
  };
  const handleApiKeyChange = (providerId: string, value: string) => {
    setApiKeysState((prev) => ({ ...prev, [providerId]: value }));
  };
  const toggleKeyVisibility = (providerId: string) => {
    setShowKeys((prev) => ({ ...prev, [providerId]: !prev[providerId] }));
  };
  const { refreshConfiguredProviders } = useJunasContext();
  const handleSaveKeys = async () => {
    setIsSaving(true);
    try {
      for (const p of PROVIDER_LIST) {
        const val = apiKeys[p.id];
        if (val && val.trim()) await setApiKey(p.id, val.trim());
      }
      await refreshConfiguredProviders();
      await loadKeys();
      await checkAllHealth();
    } catch (error) {
      console.error('Error saving API keys:', error);
    } finally {
      setIsSaving(false);
    }
  };
  const getHealthIndicator = (id: string) => {
    const status = providerHealth[id];
    if (status === 'online')
      return <div className="h-1.5 w-1.5 rounded-full bg-green-500" title="Online" />;
    if (status === 'offline')
      return <div className="h-1.5 w-1.5 rounded-full bg-red-500" title="Offline" />;
    return <div className="h-1.5 w-1.5 rounded-full bg-gray-400" title="Unconfigured" />;
  };
  return (
    <div className="space-y-4">
      <div>
        <p className="text-xs text-muted-foreground">Select a provider and configure API keys</p>
      </div>
      <div className="pt-3 space-y-3">
        {PROVIDER_LIST.map((provider) => (
          <div key={provider.id} className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Label htmlFor={`key-${provider.id}`} className="text-xs">
                  &gt; {provider.label}
                </Label>
                {getHealthIndicator(provider.id)}
              </div>
              <a
                href={provider.keyUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-primary hover:underline flex items-center gap-1"
              >
                {provider.isLocal ? 'Download' : 'Get key'} <ExternalLink className="h-3 w-3" />
              </a>
            </div>
            <div className="relative">
              <Input
                id={`key-${provider.id}`}
                type={provider.isLocal || showKeys[provider.id] ? 'text' : 'password'}
                placeholder={provider.keyPlaceholder}
                value={apiKeys[provider.id] || ''}
                onChange={(e) => handleApiKeyChange(provider.id, e.target.value)}
                className="pr-10 text-xs h-8 font-mono"
              />
              {!provider.isLocal && (
                <button
                  type="button"
                  onClick={() => toggleKeyVisibility(provider.id)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground text-xs font-mono"
                >
                  {showKeys[provider.id] ? '[hide]' : '[show]'}
                </button>
              )}
            </div>
            {(provider.id === 'ollama' || provider.id === 'lmstudio') && (
              <Alert variant="warning" className="py-2 mt-2">
                <Info className="h-4 w-4" />
                <AlertDescription className="text-xs">
                  {runtimeMode === 'tauri' ? (
                    <>
                      <strong>Desktop mode:</strong> Local providers connect directly without
                      tunneling.
                    </>
                  ) : (
                    <>
                      <strong>Browser mode:</strong> Local providers must be reachable from your
                      browser and allow cross-origin requests.
                    </>
                  )}
                </AlertDescription>
              </Alert>
            )}
          </div>
        ))}
        <div className="flex justify-end gap-2 pt-2">
          <button
            onClick={handleSaveKeys}
            disabled={isSaving}
            className="px-3 py-1 text-xs bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
          >
            [ {isSaving ? 'Saving...' : 'Save'} ]
          </button>
        </div>
      </div>
    </div>
  );
}
