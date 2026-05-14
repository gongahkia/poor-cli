export const WINDOW_EVENTS = {
  openTemplates: 'junas-open-templates',
  openRedline: 'junas-open-redline',
  openCompliance: 'junas-open-compliance',
  openClauses: 'junas-open-clauses',
  openConfigDialog: 'open-config-dialog',
} as const;

export type WindowEventName = (typeof WINDOW_EVENTS)[keyof typeof WINDOW_EVENTS];

export const CONFIG_DIALOG_TABS = [
  'profile',
  'generation',
  'localModels',
  'providers',
  'tools',
  'snippets',
  'interface',
  'developer',
] as const;

export type ConfigDialogTab = (typeof CONFIG_DIALOG_TABS)[number];

export interface OpenConfigDialogDetail {
  tab: ConfigDialogTab;
}

export type OpenConfigDialogEvent = CustomEvent<OpenConfigDialogDetail>;

export function isConfigDialogTab(value: unknown): value is ConfigDialogTab {
  return typeof value === 'string' && (CONFIG_DIALOG_TABS as readonly string[]).includes(value);
}

export function isOpenConfigDialogEvent(event: Event): event is OpenConfigDialogEvent {
  if (typeof CustomEvent === 'undefined' || !(event instanceof CustomEvent)) return false;
  return isConfigDialogTab((event.detail as { tab?: unknown } | undefined)?.tab);
}

export function emitWindowEvent(eventName: Exclude<WindowEventName, typeof WINDOW_EVENTS.openConfigDialog>): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(eventName));
}

export function emitOpenConfigDialog(tab: ConfigDialogTab): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(WINDOW_EVENTS.openConfigDialog, { detail: { tab } }));
}
