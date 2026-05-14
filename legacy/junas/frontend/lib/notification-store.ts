export type NotificationType = "error" | "info" | "success" | "warning";

export interface Notification {
  id: string;
  type: NotificationType;
  title: string;
  message: string;
  timestamp: number;
  read: boolean;
}

const STORAGE_KEY = "junas_notifications";
const MAX_STORED = 200;
let listeners: (() => void)[] = [];

function getStored(): Notification[] {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]"); }
  catch { return []; }
}
function save(list: Notification[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(list.slice(0, MAX_STORED)));
  listeners.forEach(fn => fn());
}

export function addNotification(type: NotificationType, title: string, message: string): Notification {
  const n: Notification = {
    id: `notif_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
    type, title, message, timestamp: Date.now(), read: false,
  };
  save([n, ...getStored()]);
  if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent("junas:toast", { detail: n }));
  return n;
}

export function getNotifications(): Notification[] { return getStored(); }
export function getUnreadCount(): number { return getStored().filter(n => !n.read).length; }

export function markAllRead() {
  save(getStored().map(n => ({ ...n, read: true })));
}

export function clearNotifications() { save([]); }

export function removeNotification(id: string) {
  save(getStored().filter(n => n.id !== id));
}

export function subscribe(fn: () => void) {
  listeners.push(fn);
  return () => { listeners = listeners.filter(l => l !== fn); };
}
