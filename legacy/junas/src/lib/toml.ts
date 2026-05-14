// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function parseToml(toml: string): Record<string, any> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const result: Record<string, any> = {};
  let currentSection = result;

  const lines = toml.split('\n');
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;

    // Section
    const sectionMatch = trimmed.match(/^\[(.*?)\]$/);
    if (sectionMatch) {
      const sectionName = sectionMatch[1];
      result[sectionName] = {};
      currentSection = result[sectionName];
      continue;
    }

    // Key-Value
    const kvMatch = trimmed.match(/^([\w\d_-]+)\s*=\s*(.*)$/);
    if (kvMatch) {
      const key = kvMatch[1];
      const valueStr = kvMatch[2];
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      let value: any = valueStr;

      // Handle strings
      if (valueStr.startsWith('"') && valueStr.endsWith('"')) {
        value = valueStr.slice(1, -1);
      } else if (valueStr.startsWith("'") && valueStr.endsWith("'")) {
        value = valueStr.slice(1, -1);
      }
      // Handle booleans
      else if (valueStr === 'true') value = true;
      else if (valueStr === 'false') value = false;
      // Handle numbers
      else if (!isNaN(Number(valueStr))) value = Number(valueStr);

      currentSection[key] = value;
    }
  }
  return result;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function stringifyToml(data: Record<string, any>): string {
  let toml =
    '# JUNAS CONFIGURATION FILE\n# Edit this file to configure your assistant settings.\n\n';
  const sections: string[] = [];
  const topLevel: string[] = [];

  // Separate keys into top-level and sections
  for (const [key, value] of Object.entries(data)) {
    if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
      sections.push(key);
    } else {
      if (!Array.isArray(value)) {
        topLevel.push(key);
      }
    }
  }

  // Write top level keys
  if (topLevel.length > 0) {
    toml += '# --- Global Settings ---\n';
    for (const key of topLevel) {
      const value = data[key];
      let valStr = String(value);
      if (typeof value === 'string') {
        valStr = `"${value.replace(/"/g, '\"').replace(/\n/g, '\\n')}"`;
      }
      toml += `${key} = ${valStr}\n`;
    }
    toml += '\n';
  }

  // Write sections
  for (const section of sections) {
    toml += `# --- ${section.charAt(0).toUpperCase() + section.slice(1)} Settings ---\n`;
    toml += `[${section}]\n`;
    const sectionData = data[section];
    for (const [key, value] of Object.entries(sectionData)) {
      let valStr = String(value);
      if (typeof value === 'string') {
        valStr = `"${value.replace(/"/g, '\"').replace(/\n/g, '\\n')}"`;
      }
      toml += `${key} = ${valStr}\n`;
    }
    toml += '\n';
  }

  return toml;
}
