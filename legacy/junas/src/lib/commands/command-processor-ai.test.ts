import { describe, expect, it } from 'vitest';
import { parseCommand, processLocalCommand, COMMANDS } from '@/lib/commands/command-processor';

describe('AI slash commands', () => {
  const aiCommands = [
    'search-case-law',
    'research-statute',
    'analyze-contract',
    'summarize-document',
    'draft-clause',
    'check-compliance',
    'due-diligence-review',
  ] as const;

  it('all 7 AI commands are marked as implemented', () => {
    for (const cmd of aiCommands) {
      const info = COMMANDS.find((c) => c.id === cmd);
      expect(info, `${cmd} should exist`).toBeDefined();
      expect(info!.implemented, `${cmd} should be implemented`).toBe(true);
      expect(info!.isLocal, `${cmd} should be non-local`).toBe(false);
    }
  });

  it('parses AI commands with args', () => {
    const parsed = parseCommand('/analyze-contract This is a contract between A and B.');
    expect(parsed).not.toBeNull();
    expect(parsed!.command).toBe('analyze-contract');
    expect(parsed!.args).toContain('contract between A and B');
    expect(parsed!.isLocal).toBe(false);
  });

  it('routes AI commands through sync processor as __ASYNC_MODEL_COMMAND__', () => {
    for (const cmd of aiCommands) {
      const result = processLocalCommand({ command: cmd, args: 'test input', isLocal: true });
      expect(result.content, `${cmd} should return async signal`).toBe('__ASYNC_MODEL_COMMAND__');
      expect(result.success).toBe(true);
    }
  });

  it('rejects empty args', () => {
    const result = processLocalCommand({ command: 'analyze-contract', args: '', isLocal: true });
    expect(result.success).toBe(false);
    expect(result.content).toContain('provide text');
  });
});

describe('command definitions integrity', () => {
  it('all commands have unique ids', () => {
    const ids = COMMANDS.map((c) => c.id);
    expect(new Set(ids).size).toBe(ids.length);
  });
  it('all commands have non-empty descriptions', () => {
    for (const cmd of COMMANDS) {
      expect(cmd.description.length, `${cmd.id} needs description`).toBeGreaterThan(0);
    }
  });
});
