"use client";
import { useTheme } from "../lib/theme-provider";

export default function ThemeToggle() {
  const { darkMode, setDarkMode } = useTheme();
  const next = darkMode === "dark" ? "light" : "dark";
  return (
    <button type="button" onClick={() => setDarkMode(next as any)} aria-label={`Switch to ${next} mode`}
      style={{
        background: "none", border: "1px solid var(--border, #E7E5E4)", borderRadius: "0.4rem",
        padding: "0.25rem 0.45rem", cursor: "pointer", fontSize: "0.78rem", lineHeight: 1,
        color: "var(--muted-foreground, #78716C)", fontFamily: "inherit",
      }}>
      {darkMode === "dark" ? "Light" : "Dark"}
    </button>
  );
}
