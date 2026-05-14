import { useEffect, useState } from 'react';
import { getModelsWithStatus, AVAILABLE_MODELS } from '@/lib/ml/model-manager';
import { getApiKey } from '@/lib/tauri-bridge';
import { PROVIDER_LIST } from '@/lib/providers/registry';

export function ModelProviderStatus() {
  const [modelCount, setModelCount] = useState(0);
  const [areAllModelsDownloaded, setAreAllModelsDownloaded] = useState(false);
  const [providerCount, setProviderCount] = useState(0);
  const [providerNames, setProviderNames] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchStatus() {
      // Local models
      const models = await getModelsWithStatus();
      const downloadedCount = models.filter((m) => m.isDownloaded).length;
      setModelCount(downloadedCount);
      setAreAllModelsDownloaded(downloadedCount === AVAILABLE_MODELS.length);

      // Providers via keychain-backed Tauri commands
      try {
        const names: string[] = [];
        for (const provider of PROVIDER_LIST) {
          try {
            const keyOrEndpoint = await getApiKey(provider.id);
            if (keyOrEndpoint?.trim()) {
              names.push(provider.label);
            }
          } catch {
            // provider not configured
          }
        }
        setProviderCount(names.length);
        setProviderNames(names);
      } catch {
        setProviderCount(0);
        setProviderNames([]);
      }
      setLoading(false);
    }
    fetchStatus();
  }, []);

  if (loading) return <span className="text-xs text-muted-foreground">[ ... ]</span>;

  if (areAllModelsDownloaded) {
    return <span className="text-xs text-muted-foreground">[ Local Models ]</span>;
  }

  if (modelCount === 0 && providerCount === 0)
    return <span className="text-xs text-muted-foreground">[ No models ✗ ]</span>;

  const parts = [];
  if (modelCount > 0) parts.push(`${modelCount} local model${modelCount > 1 ? 's' : ''}`);
  if (providerCount > 0) parts.push(`${providerNames.join(', ')} API`);

  return <span className="text-xs text-muted-foreground">[ {parts.join(' • ')} ]</span>;
}
