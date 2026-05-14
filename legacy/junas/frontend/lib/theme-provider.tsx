"use client";
import { createContext, useContext, useEffect, useState } from "react";

export type ColorTheme = "vanilla" | "ocean" | "forest" | "rose" | "midnight" | "slate";
export type DarkMode = "light" | "dark" | "system";

interface ThemeState {
  colorTheme: ColorTheme;
  darkMode: DarkMode;
  focusMode: boolean;
  setColorTheme: (t: ColorTheme) => void;
  setDarkMode: (m: DarkMode) => void;
  setFocusMode: (f: boolean) => void;
  // legacy compat
  theme: DarkMode;
  setTheme: (t: DarkMode) => void;
}

const ThemeContext = createContext<ThemeState>({
  colorTheme: "vanilla", darkMode: "light", focusMode: false,
  setColorTheme: () => {}, setDarkMode: () => {}, setFocusMode: () => {},
  theme: "light", setTheme: () => {},
});

export function useTheme() { return useContext(ThemeContext); }

export const COLOR_THEMES: { id: ColorTheme; label: string }[] = [
  { id: "vanilla", label: "Vanilla" },
  { id: "ocean", label: "Ocean" },
  { id: "forest", label: "Forest" },
  { id: "rose", label: "Rose" },
  { id: "midnight", label: "Midnight" },
  { id: "slate", label: "Slate" },
];

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [colorTheme, setColorThemeState] = useState<ColorTheme>("vanilla");
  const [darkMode, setDarkModeState] = useState<DarkMode>("light");
  const [focusMode, setFocusModeState] = useState(false);

  useEffect(() => {
    const ct = localStorage.getItem("junas-color-theme") as ColorTheme | null;
    const dm = (localStorage.getItem("junas-theme") as DarkMode | null) || "light";
    const fm = localStorage.getItem("junas-focus-mode") === "true";
    if (ct) setColorThemeState(ct);
    setDarkModeState(dm);
    setFocusModeState(fm);
    applyAll(ct || "vanilla", dm, fm);
  }, []);

  const setColorTheme = (t: ColorTheme) => {
    setColorThemeState(t);
    localStorage.setItem("junas-color-theme", t);
    applyAll(t, darkMode, focusMode);
  };
  const setDarkMode = (m: DarkMode) => {
    setDarkModeState(m);
    localStorage.setItem("junas-theme", m);
    applyAll(colorTheme, m, focusMode);
  };
  const setFocusMode = (f: boolean) => {
    setFocusModeState(f);
    localStorage.setItem("junas-focus-mode", String(f));
    applyAll(colorTheme, darkMode, f);
  };

  return (
    <ThemeContext.Provider value={{
      colorTheme, darkMode, focusMode,
      setColorTheme, setDarkMode, setFocusMode,
      theme: darkMode, setTheme: setDarkMode,
    }}>
      {children}
    </ThemeContext.Provider>
  );
}

function applyAll(colorTheme: ColorTheme, darkMode: DarkMode, focusMode: boolean) {
  const root = document.documentElement;
  // dark mode
  const isDark = darkMode === "dark" || (darkMode === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  root.classList.toggle("dark", isDark);
  // color theme
  COLOR_THEMES.forEach(t => root.classList.remove(`theme-${t.id}`));
  if (colorTheme !== "vanilla") root.classList.add(`theme-${colorTheme}`);
  // focus mode
  root.classList.toggle("focus-mode", focusMode);
}
