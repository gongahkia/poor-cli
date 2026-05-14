/**
 * Migration utility for legacy browser key storage.
 * Moves old bundled key payloads into per-provider encrypted keys used by the current runtime adapters.
 */
import { isTauriRuntime } from '@/lib/runtime';
import { setApiKey } from '@/lib/tauri-bridge';

const WEB_KEY_PREFIX = 'junas_web_api_key_';

export async function migrateApiKeysToSession(): Promise<boolean> {
  try {
    if (isTauriRuntime()) {
      localStorage.setItem('junas_keys_migrated', 'true');
      return true;
    }
    const migrated = localStorage.getItem('junas_keys_migrated');
    if (migrated === 'true') {
      // re-encrypt any plaintext keys left from before encryption was added
      await reEncryptPlaintextKeys();
      return true;
    }
    const oldKeysStr = localStorage.getItem('junas_api_keys');
    if (!oldKeysStr) {
      localStorage.setItem('junas_keys_migrated', 'true');
      return true;
    }
    try {
      const oldKeys = JSON.parse(oldKeysStr) as Record<string, unknown>;
      for (const [provider, key] of Object.entries(oldKeys)) {
        if (typeof key === 'string' && key.trim().length > 0) {
          await setApiKey(provider, key.trim()); // stores encrypted
        }
      }
      localStorage.removeItem('junas_api_keys');
      localStorage.setItem('junas_keys_migrated', 'true');
      localStorage.setItem('junas_keys_encrypted', 'true');
      return true;
    } catch (error) {
      console.error('Error parsing old API keys:', error);
      return false;
    }
  } catch (error) {
    console.error('Migration error:', error);
    return false;
  }
}

async function reEncryptPlaintextKeys(): Promise<void> {
  if (localStorage.getItem('junas_keys_encrypted') === 'true') return;
  const providers = ['openai', 'claude', 'gemini', 'serper'];
  for (const provider of providers) {
    const raw = localStorage.getItem(`${WEB_KEY_PREFIX}${provider}`);
    if (!raw) continue;
    try { atob(raw); continue; } catch { /* not base64 = plaintext, re-encrypt */ }
    if (raw.startsWith('sk-') || raw.startsWith('AIza') || raw.length > 10) {
      await setApiKey(provider, raw); // re-stores as encrypted
    }
  }
  localStorage.setItem('junas_keys_encrypted', 'true');
}

export function needsMigration(): boolean {
  if (isTauriRuntime()) return false;
  const migrated = localStorage.getItem('junas_keys_migrated');
  const hasOldKeys = localStorage.getItem('junas_api_keys');
  const encrypted = localStorage.getItem('junas_keys_encrypted');
  return (migrated !== 'true' && !!hasOldKeys) || encrypted !== 'true';
}
