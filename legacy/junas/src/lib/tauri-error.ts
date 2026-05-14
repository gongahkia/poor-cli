export interface TauriAppError {
  code: string;
  message: string;
}

type TauriErrorLike = {
  code?: unknown;
  message?: unknown;
};

const RECOVERY_HINTS: Record<string, string> = {
  KEYCHAIN_ERROR: 'Re-save the affected API key in Settings and try again.',
  NETWORK_ERROR: 'Check your internet connection and endpoint, then retry.',
  PROVIDER_ERROR: 'Verify provider API key, model selection, and provider availability.',
  PARSE_ERROR: 'Check the input format and try again.',
  IO_ERROR: 'Check local file permissions and available disk space.',
};

export function toTauriAppError(error: unknown): TauriAppError {
  if (typeof error === 'string') {
    return { code: 'UNKNOWN_ERROR', message: error };
  }

  if (error && typeof error === 'object') {
    const maybe = error as TauriErrorLike;
    if (typeof maybe.code === 'string' && typeof maybe.message === 'string') {
      return { code: maybe.code, message: maybe.message };
    }
    if (typeof maybe.message === 'string') {
      return { code: 'UNKNOWN_ERROR', message: maybe.message };
    }
  }

  return { code: 'UNKNOWN_ERROR', message: String(error) };
}

export function toActionableToastDescription(error: unknown, fallback: string): string {
  const normalized = toTauriAppError(error);
  const hint =
    RECOVERY_HINTS[normalized.code] || 'Retry and review app logs if the issue persists.';
  const baseMessage = normalized.message || fallback;
  return `${baseMessage} (${normalized.code}) ${hint}`;
}

export function toErrorWithCode(error: unknown): Error & { code: string } {
  const normalized = toTauriAppError(error);
  const wrapped = new Error(normalized.message) as Error & { code: string };
  wrapped.code = normalized.code;
  return wrapped;
}
