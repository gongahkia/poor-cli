import { describe, expect, it } from 'vitest';
import { parseToml, stringifyToml } from '@/lib/toml';

describe('TOML parser', () => {
  it('parses section headers and values correctly', () => {
    const parsed = parseToml(`
temperature = 0.7

[profile]
userRole = "lawyer"
userPurpose = "due diligence"
`);

    expect(parsed.temperature).toBe(0.7);
    expect(parsed.profile).toEqual({
      userRole: 'lawyer',
      userPurpose: 'due diligence',
    });
  });

  it('stringifies section data into TOML format', () => {
    const output = stringifyToml({
      temperature: 0.9,
      profile: { userRole: 'student' },
    });

    expect(output).toContain('[profile]');
    expect(output).toContain('temperature = 0.9');
    expect(output).toContain('userRole = "student"');
  });
});
