"use client";
import { useState, useEffect } from "react";
import {
  getNotifications, getUnreadCount, markAllRead, clearNotifications,
  removeNotification, subscribe, type Notification,
} from "../lib/notification-store";

const TYPE_LABELS: Record<string, string> = { error: "Error", warning: "Warning", success: "Success", info: "Info" };

function formatTime(ts: number): string {
  const diff = Date.now() - ts;
  if (diff < 60000) return "just now";
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(ts));
}

interface Props { isOpen: boolean; onClose: () => void; }

export default function NotificationsPanel({ isOpen, onClose }: Props) {
  const [notifications, setNotifications] = useState<Notification[]>([]);

  useEffect(() => {
    if (isOpen) {
      setNotifications(getNotifications());
      markAllRead();
    }
  }, [isOpen]);

  useEffect(() => {
    return subscribe(() => setNotifications(getNotifications()));
  }, []);

  if (!isOpen) return null;

  const handleClear = () => { clearNotifications(); setNotifications([]); };
  const handleRemove = (id: string) => { removeNotification(id); setNotifications(getNotifications()); };

  return (
    <div className="notif-overlay" onClick={onClose}>
      <div className="notif-panel" onClick={e => e.stopPropagation()}>
        <div className="notif-header">
          <span className="notif-header-title">Notifications</span>
          <div style={{ display: "flex", gap: "0.35rem" }}>
            {notifications.length > 0 && (
              <button type="button" className="notif-clear-btn" onClick={handleClear}>Clear all</button>
            )}
            <button type="button" className="notif-close-btn" onClick={onClose}>&times;</button>
          </div>
        </div>
        <div className="notif-list">
          {notifications.length === 0 && (
            <div className="notif-empty">No notifications</div>
          )}
          {notifications.map(n => (
            <div key={n.id} className={`notif-item notif-item-${n.type}`}>
              <div className="notif-item-header">
                <span className={`notif-type-badge notif-type-${n.type}`}>{TYPE_LABELS[n.type]}</span>
                <span className="notif-time">{formatTime(n.timestamp)}</span>
              </div>
              <div className="notif-item-title">{n.title}</div>
              {n.message && <div className="notif-item-message">{n.message}</div>}
              <button type="button" className="notif-item-remove" onClick={() => handleRemove(n.id)}>&times;</button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function useUnreadCount() {
  const [count, setCount] = useState(0);
  useEffect(() => {
    setCount(getUnreadCount());
    return subscribe(() => setCount(getUnreadCount()));
  }, []);
  return count;
}
