type RuntimeWindow = Window & {
  __TAURI_INTERNALS__?: unknown;
  __TAURI__?: unknown;
};

export function isBrowserEnvironment(): boolean {
  return typeof window !== 'undefined';
}

export function isTauriRuntime(): boolean {
  if (!isBrowserEnvironment()) return false;
  const runtimeWindow = window as RuntimeWindow;
  return Boolean(runtimeWindow.__TAURI_INTERNALS__ || runtimeWindow.__TAURI__);
}

export function getRuntimeMode(): 'tauri' | 'web' {
  return isTauriRuntime() ? 'tauri' : 'web';
}
