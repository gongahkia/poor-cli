"use client";
import { useEffect } from "react";

interface ShortcutMap {
  onCommandPalette?: () => void;
  onNewChat?: () => void;
  onSend?: () => void;
}

export function useKeyboardShortcuts(shortcuts: ShortcutMap) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key === "k") { e.preventDefault(); shortcuts.onCommandPalette?.(); }
      if (mod && e.key === "n") { e.preventDefault(); shortcuts.onNewChat?.(); }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [shortcuts]);
}
