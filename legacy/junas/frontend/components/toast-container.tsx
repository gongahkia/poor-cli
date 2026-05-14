"use client";
import { useState, useEffect, useCallback } from "react";
import type { Notification } from "../lib/notification-store";

const ICONS: Record<string, string> = {
  error: "\u2716",   // ✖
  warning: "\u26A0", // ⚠
  success: "\u2714", // ✔
  info: "\u2139",    // ℹ
};

export default function ToastContainer() {
  const [toasts, setToasts] = useState<(Notification & { exiting?: boolean })[]>([]);

  useEffect(() => {
    const handler = (e: Event) => {
      const n = (e as CustomEvent).detail as Notification;
      setToasts(prev => [...prev, n]);
      const duration = n.type === "error" ? 8000 : 5000;
      setTimeout(() => {
        setToasts(prev => prev.map(t => t.id === n.id ? { ...t, exiting: true } : t));
        setTimeout(() => setToasts(prev => prev.filter(t => t.id !== n.id)), 300);
      }, duration);
    };
    window.addEventListener("junas:toast", handler);
    return () => window.removeEventListener("junas:toast", handler);
  }, []);

  const dismiss = useCallback((id: string) => {
    setToasts(prev => prev.map(t => t.id === id ? { ...t, exiting: true } : t));
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 300);
  }, []);

  if (toasts.length === 0) return null;

  return (
    <div className="toast-container">
      {toasts.map(t => (
        <div key={t.id} className={`toast toast-${t.type} ${t.exiting ? "toast-exit" : ""}`}>
          <span className="toast-icon">{ICONS[t.type]}</span>
          <div className="toast-body">
            <div className="toast-title">{t.title}</div>
            {t.message && <div className="toast-message">{t.message}</div>}
          </div>
          <button type="button" className="toast-dismiss" onClick={() => dismiss(t.id)}>&times;</button>
        </div>
      ))}
    </div>
  );
}
