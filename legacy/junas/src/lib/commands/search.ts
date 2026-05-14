import Fuse from 'fuse.js';
import { COMMANDS, CommandInfo } from './definitions';

const COMMAND_FUSE_OPTIONS: Fuse.IFuseOptions<CommandInfo> = {
  keys: ['id', 'label', 'description', 'category'],
  threshold: 0.4,
  distance: 100,
};

export function getAvailableCommands(onnxAvailable: boolean): CommandInfo[] {
  return COMMANDS.filter((command) => onnxAvailable || !command.requiresOnnx);
}

export function createCommandSearch(commands: CommandInfo[]): Fuse<CommandInfo> {
  return new Fuse(commands, COMMAND_FUSE_OPTIONS);
}

export function getCommandMatches(
  query: string,
  commands: CommandInfo[],
  searchIndex: Fuse<CommandInfo>
): CommandInfo[] {
  const normalizedQuery = query.trim();
  if (!normalizedQuery) return commands;
  return searchIndex.search(normalizedQuery).map((result) => result.item);
}
