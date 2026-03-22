import { readFileSync } from "node:fs";
import { join } from "node:path";

const skillPath = join(import.meta.dirname ?? ".", "..", "packages", "skill", "SKILL.md");

try {
  const content = readFileSync(skillPath, "utf-8");

  // Check frontmatter
  const fmMatch = content.match(/^---\n([\s\S]*?)\n---/);
  if (fmMatch === null) {
    process.stderr.write("ERROR: Missing frontmatter\n");
    process.exit(1);
  }

  const frontmatter = fmMatch[1]!;
  const required = ["name", "description", "version", "mcp_server"];
  for (const field of required) {
    if (!frontmatter.includes(`${field}:`)) {
      process.stderr.write(`ERROR: Missing frontmatter field: ${field}\n`);
      process.exit(1);
    }
  }

  // Check for tool documentation
  const toolNames = [
    "sg_singstat_search", "sg_singstat_table", "sg_singstat_timeseries",
    "sg_mas_exchange_rates", "sg_mas_interest_rates",
    "sg_onemap_geocode", "sg_onemap_route", "sg_onemap_population",
    "sg_ura_property_transactions",
    "sg_datagov_search", "sg_datagov_get",
    "sg_health_check", "sg_key_set", "sg_cache_stats",
  ];

  for (const tool of toolNames) {
    if (!content.includes(tool)) {
      process.stderr.write(`WARNING: Tool not documented in SKILL.md: ${tool}\n`);
    }
  }

  // Check for unclosed code blocks
  const codeBlocks = (content.match(/```/g) ?? []).length;
  if (codeBlocks % 2 !== 0) {
    process.stderr.write("ERROR: Unclosed code block in SKILL.md\n");
    process.exit(1);
  }

  process.stderr.write("SKILL.md validation passed\n");
  process.exit(0);
} catch (error) {
  process.stderr.write(`ERROR: ${error}\n`);
  process.exit(1);
}
