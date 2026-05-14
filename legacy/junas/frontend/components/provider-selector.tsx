"use client";
import { useState, useEffect, useRef } from "react";

const PROVIDERS = [
  { id: "claude", label: "Claude", keyName: "junas_apikey_claude" },
  { id: "openai", label: "OpenAI", keyName: "junas_apikey_openai" },
  { id: "gemini", label: "Gemini", keyName: "junas_apikey_gemini" },
  { id: "ollama", label: "Ollama (Local)", keyName: "junas_apikey_ollama", local: true },
  { id: "lmstudio", label: "LM Studio (Local)", keyName: "junas_apikey_lmstudio", local: true },
];

// chip/gear icon SVG matching the screenshot
function ProviderIcon() {
  return (
    <svg className="provider-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3">
      <rect x="3" y="3" width="10" height="10" rx="2" />
      <circle cx="6" cy="8" r="1" fill="currentColor" stroke="none" />
      <circle cx="10" cy="8" r="1" fill="currentColor" stroke="none" />
      <line x1="6" y1="5" x2="6" y2="3" /><line x1="10" y1="5" x2="10" y2="3" />
      <line x1="6" y1="13" x2="6" y2="11" /><line x1="10" y1="13" x2="10" y2="11" />
      <line x1="3" y1="6" x2="1" y2="6" /><line x1="3" y1="10" x2="1" y2="10" />
      <line x1="13" y1="6" x2="15" y2="6" /><line x1="13" y1="10" x2="15" y2="10" />
    </svg>
  );
}

interface Props {
  value: string;
  onChange: (provider: string) => void;
}

export default function ProviderSelector({ value, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const [statuses, setStatuses] = useState<Record<string, boolean>>({});
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const s: Record<string, boolean> = {};
    PROVIDERS.forEach(p => {
      if (p.local) { s[p.id] = true; return; } // local always green
      s[p.id] = !!localStorage.getItem(p.keyName);
    });
    setStatuses(s);
  }, [open]); // recheck when opening

  // close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const current = PROVIDERS.find(p => p.id === value) || PROVIDERS[0];

  return (
    <div className="provider-dropdown" ref={ref}>
      <button type="button" className="provider-trigger" onClick={() => setOpen(v => !v)}>
        <ProviderIcon />
        <span>{current.label}</span>
        <span className={`provider-dot ${statuses[current.id] ? "provider-dot-green" : "provider-dot-red"}`} />
      </button>
      {open && (
        <div className="provider-menu">
          {PROVIDERS.map(p => (
            <button key={p.id} type="button" className="provider-option"
              onClick={() => { onChange(p.id); setOpen(false); }}>
              <ProviderIcon />
              <span>{p.label}</span>
              <span className={`provider-dot ${statuses[p.id] ? "provider-dot-green" : "provider-dot-red"}`} />
              {p.id === value && (
                <span className="provider-option-check">&#10003;</span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
