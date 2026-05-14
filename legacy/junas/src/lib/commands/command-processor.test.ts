import { describe, expect, it } from 'vitest';
import { parseCommand } from '@/lib/commands/command-processor';

describe('command parsing', () => {
  it('parses valid slash commands with arguments', () => {
    const parsed = parseCommand('/extract-entities John Tan v ABC Pte Ltd');

    expect(parsed).toEqual({
      command: 'extract-entities',
      args: 'John Tan v ABC Pte Ltd',
      isLocal: true,
    });
  });

  it('returns null for unknown commands', () => {
    expect(parseCommand('/not-a-real-command something')).toBeNull();
  });

  it('supports multiline arguments for command payloads', () => {
    const parsed = parseCommand('/analyze-document Clause 1\nClause 2\nClause 3');

    expect(parsed?.command).toBe('analyze-document');
    expect(parsed?.args).toContain('Clause 2');
  });
});
