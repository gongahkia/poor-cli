"use client";
import { useMemo } from "react";
import { COMMAND_DEFINITIONS } from "../../lib/commands/definitions";

export interface CommandDef {
  id: string;
  label: string;
  description: string;
  category: string;
}

export const COMMANDS: CommandDef[] = COMMAND_DEFINITIONS.reduce<CommandDef[]>(
  (acc, definition) => {
    if (definition.action.kind !== "command") return acc;
    acc.push({
      id: definition.action.commandId,
      label: definition.label,
      description: definition.description,
      category: `${definition.category[0].toUpperCase()}${definition.category.slice(1)}`,
    });
    return acc;
  },
  [],
);

const normalizeQuery = (value: string) => value.trim().toLowerCase();

export const filterCommands = (query: string, commands: CommandDef[] = COMMANDS) => {
  const normalized = normalizeQuery(query);
  if (!normalized) return commands;
  return commands.filter((command) => {
    const haystacks = [command.id, command.label, command.description, command.category];
    return haystacks.some((field) => field.toLowerCase().includes(normalized));
  });
};

interface Props {
  query: string;
  onSelect: (commandId: string) => void;
  isOpen: boolean;
  selectedIndex: number;
}

export default function CommandSuggestions({ query, onSelect, isOpen, selectedIndex }: Props) {
  const matches = useMemo(() => filterCommands(query), [query]);
  if (!isOpen) return null;
  const selectedMatchIndex = matches.length === 0 ? -1 : Math.min(selectedIndex, matches.length - 1);

  return (
    <div className="cmd-suggestions">
      {matches.length === 0 && (
        <div style={{ padding: "0.75rem", fontSize: "0.8rem" }} className="cmd-suggestion-desc">No matching commands</div>
      )}
      {matches.map((cmd, i) => (
        <div key={cmd.id} onClick={() => onSelect(cmd.id)}
          className={`cmd-suggestion-item ${i === selectedMatchIndex ? "selected" : ""}`}>
          <span className="cmd-suggestion-id">/{cmd.id}</span>
          <span className="cmd-suggestion-desc">{cmd.description}</span>
          <span className="cmd-suggestion-cat">{cmd.category}</span>
        </div>
      ))}
    </div>
  );
}
