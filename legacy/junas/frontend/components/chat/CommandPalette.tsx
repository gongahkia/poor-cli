"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  COMMAND_DEFINITIONS,
  type CommandDefinition,
  getCommandSections,
  matchesCommandQuery,
} from "../../lib/commands/definitions";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onSelectCommand: (cmdId: string) => void;
  onNewChat: () => void;
}

function clickButtonByText(text: string): void {
  const buttons = Array.from(document.querySelectorAll<HTMLButtonElement>("button"));
  const button = buttons.find((candidate) => candidate.textContent?.trim() === text);
  button?.click();
}

async function shareCurrentPage(): Promise<void> {
  const url = window.location.href;
  if (navigator.share) {
    await navigator.share({ title: document.title, url });
    return;
  }
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(url);
  }
}

export default function CommandPalette({ isOpen, onClose, onSelectCommand, onNewChat }: Props) {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(0);

  const filteredCommands = useMemo(() => COMMAND_DEFINITIONS.filter((definition) => matchesCommandQuery(definition, query)), [query]);
  const sections = useMemo(() => getCommandSections(filteredCommands), [filteredCommands]);
  const flatCommands = useMemo(() => sections.flatMap((section) => section.commands), [sections]);
  const indexById = useMemo(() => new Map(flatCommands.map((command, index) => [command.id, index])), [flatCommands]);

  const execute = useCallback(
    (command: CommandDefinition | undefined): void => {
      if (!command) return;

      onClose();
      switch (command.action.kind) {
        case "command":
          onSelectCommand(command.action.commandId);
          return;
        case "navigate":
          window.location.assign(command.action.href);
          return;
        case "new-chat":
          onNewChat();
          return;
        case "click-by-text":
          clickButtonByText(command.action.text);
          return;
        case "share":
          void shareCurrentPage().catch(() => undefined);
          return;
      }
    },
    [onClose, onNewChat, onSelectCommand],
  );

  useEffect(() => {
    if (isOpen) {
      setQuery("");
      setSelected(0);
    }
  }, [isOpen]);

  useEffect(() => {
    if (flatCommands.length === 0) {
      setSelected(0);
      return;
    }
    setSelected((current) => Math.min(current, flatCommands.length - 1));
  }, [flatCommands.length]);

  useEffect(() => {
    if (!isOpen) return;

    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setSelected((current) => (flatCommands.length === 0 ? 0 : Math.min(current + 1, flatCommands.length - 1)));
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        setSelected((current) => (flatCommands.length === 0 ? 0 : Math.max(current - 1, 0)));
        return;
      }
      if (event.key === "Enter") {
        event.preventDefault();
        execute(flatCommands[selected]);
      }
    };

    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [execute, flatCommands, isOpen, onClose, selected]);

  if (!isOpen) return null;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 100,
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "center",
        paddingTop: "15vh",
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: "var(--color-scheme, #fff)",
          border: "1px solid #cbd5e1",
          borderRadius: "0.9rem",
          boxShadow: "0 20px 60px rgba(0,0,0,0.2)",
          width: "560px",
          maxHeight: "500px",
          overflow: "hidden",
        }}
        onClick={(event) => event.stopPropagation()}
      >
        <div style={{ padding: "0.7rem", borderBottom: "1px solid #e2e8f0" }}>
          <input
            autoFocus
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setSelected(0);
            }}
            placeholder="Type a command or search..."
            style={{
              width: "100%",
              padding: "0.55rem 0.65rem",
              border: "none",
              outline: "none",
              fontSize: "0.92rem",
              background: "transparent",
            }}
          />
        </div>

        <div style={{ maxHeight: "420px", overflowY: "auto", padding: "0.35rem 0" }}>
          {sections.length === 0 ? (
            <div style={{ padding: "1rem", textAlign: "center", color: "#94a3b8", fontSize: "0.85rem" }}>No results</div>
          ) : (
            sections.map((section) => (
              <div key={section.category} style={{ padding: "0.2rem 0" }}>
                <div style={{ padding: "0.35rem 0.85rem 0.25rem", fontSize: "0.68rem", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "#64748b" }}>
                  {section.label}
                </div>
                <div style={{ display: "grid" }}>
                  {section.commands.map((command) => {
                    const index = indexById.get(command.id) ?? -1;
                    const isSelected = index === selected;
                    const Icon = command.icon;

                    return (
                      <button
                        key={command.id}
                        type="button"
                        onClick={() => execute(command)}
                        style={{
                          width: "100%",
                          padding: "0.6rem 0.85rem",
                          cursor: "pointer",
                          display: "flex",
                          alignItems: "center",
                          gap: "0.75rem",
                          border: "none",
                          textAlign: "left",
                          background: isSelected ? "#dbeafe" : "transparent",
                        }}
                      >
                        <span
                          aria-hidden="true"
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            justifyContent: "center",
                            width: "1.8rem",
                            height: "1.8rem",
                            borderRadius: "0.55rem",
                            background: isSelected ? "#bfdbfe" : "#eff6ff",
                            color: "#1d4ed8",
                            flexShrink: 0,
                          }}
                        >
                          <Icon size={15} />
                        </span>
                        <span style={{ minWidth: 0, flex: 1 }}>
                          <span style={{ display: "block", fontWeight: 600, fontSize: "0.88rem", color: "#0f172a" }}>
                            {command.label}
                          </span>
                          <span style={{ display: "block", fontSize: "0.8rem", color: "#64748b" }}>{command.description}</span>
                        </span>
                        {command.action.kind === "command" && (
                          <span style={{ fontSize: "0.65rem", color: "#94a3b8", fontWeight: 600, fontFamily: "monospace" }}>
                            /{command.id}
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
