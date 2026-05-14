/**
 * Chat command handler — wires /commands to backend API endpoints.
 */
import {
  checkCompliance,
  searchCases,
  extractEntities,
  classifyContract,
  searchStatutes,
  listClauses,
  listTemplates,
} from "../api-client";

interface CommandResult { isCommand: boolean; response?: string; }

export async function handleCommand(input: string): Promise<CommandResult> {
  const match = input.match(/^\/(\S+)\s*([\s\S]*)$/);
  if (!match) return { isCommand: false };
  const [, cmd, text] = match;
  const trimmed = text.trim();
  if (!trimmed && !["use-template"].includes(cmd)) return { isCommand: true, response: `Command /${cmd} requires text input.` };

  try {
    switch (cmd) {
      case "check-compliance": {
        const data = await checkCompliance(trimmed);
        return { isCommand: true, response: formatCompliance(data) };
      }
      case "search-case-law": {
        const data = await searchCases(trimmed, 5);
        return { isCommand: true, response: formatCaseResults(data) };
      }
      case "extract-entities": {
        const data = await extractEntities(trimmed);
        return { isCommand: true, response: formatEntities(data) };
      }
      case "analyze-contract": {
        const data = await classifyContract(trimmed);
        return { isCommand: true, response: formatContractAnalysis(data) };
      }
      case "search-statute":
      case "research-statute": {
        const data = await searchStatutes(trimmed);
        return { isCommand: true, response: formatStatuteResults(data) };
      }
      case "summarize-document":
        return { isCommand: true, response: summarizeDocumentHeuristically(trimmed) };
      case "analyze-document":
        return { isCommand: true, response: analyzeDocument(trimmed) };
      case "due-diligence-review":
        return { isCommand: true, response: buildDueDiligenceReview(trimmed) };
      case "draft-clause":
        return { isCommand: true, response: await draftClauseFromLibrary(trimmed) };
      case "use-template":
        return { isCommand: true, response: await listTemplateOptions(trimmed) };
      case "redline":
        return { isCommand: true, response: compareDrafts(trimmed) };
      default:
        return { isCommand: false };
    }
  } catch (err: any) {
    return { isCommand: true, response: `**Error:** ${err.message || "Command failed"}` };
  }
}

function formatCompliance(data: any): string {
  if (data.error) return `**Compliance Error:** ${data.error}`;
  const s = data.summary || {};
  let md = `## Compliance Check Results\n\n**Passed:** ${s.passed || 0} | **Warnings:** ${s.warnings || 0} | **Failed:** ${s.failed || 0}\n\n`;
  for (const r of data.results || []) {
    const status = String(r.status || "unknown").toUpperCase();
    md += `- [${status}] **${r.rule_name}** (${r.severity}) — ${r.details}\n`;
  }
  return md;
}

function formatCaseResults(data: any): string {
  if (data.error) return `**Search Error:** ${data.error}`;
  const results = data.results || data.cases || [];
  if (results.length === 0) return "No case results found.";
  let md = `## Case Law Results\n\n`;
  for (const r of results.slice(0, 10)) {
    const title = r.title || r.case_name || r.source_id || "Unknown";
    const rawScore = Number(r.score ?? r.relevance_score ?? 0);
    const score = rawScore > 0 ? ` (score: ${rawScore.toFixed(3)})` : "";
    md += `- **${title}**${score}\n`;
    const snippet = r.text || r.snippet || r.facts || r.judgment || "";
    if (snippet) md += `  > ${String(snippet).slice(0, 220)}...\n\n`;
  }
  return md;
}

function formatEntities(data: any): string {
  if (data.error) return `**NER Error:** ${data.error}`;
  const entities = data.entities || [];
  if (entities.length === 0) return "No entities found.";
  let md = `## Extracted Entities (${entities.length})\n\n`;
  const grouped: Record<string, string[]> = {};
  for (const e of entities) {
    const label = e.label || e.type || "UNKNOWN";
    if (!grouped[label]) grouped[label] = [];
    grouped[label].push(e.text || e.word || "");
  }
  for (const [label, texts] of Object.entries(grouped)) {
    md += `**${label}:** ${Array.from(new Set(texts)).join(", ")}\n\n`;
  }
  return md;
}

function formatContractAnalysis(data: any): string {
  if (data.error) return `**Analysis Error:** ${data.error}`;
  const clauses = data.clauses || [];
  if (clauses.length > 0) {
    let md = `## Contract Clause Analysis\n\n`;
    for (const clause of clauses.slice(0, 8)) {
      const label = clause.clause_type || "Unknown";
      const score = Number(clause.confidence ?? 0);
      const confidence = score > 0 ? ` (${(score * 100).toFixed(1)}%)` : "";
      md += `- **${label}**${confidence}\n`;
      md += `  > ${String(clause.text || "").slice(0, 180)}...\n`;
    }
    return md;
  }

  const types = data.clause_types || data.predictions || [];
  if (types.length === 0) return "No clause types detected.";
  let md = `## Contract Clause Analysis\n\n`;
  for (const t of types) {
    const label = t.label || t.type || "Unknown";
    const score = Number(t.score ?? 0);
    const confidence = score > 0 ? ` — ${(score * 100).toFixed(1)}%` : "";
    md += `- **${label}**${confidence}\n`;
  }
  return md;
}

function formatStatuteResults(data: any): string {
  if (data.error) return `**Search Error:** ${data.error}`;
  const results = data.results || [];
  if (results.length === 0) return "No statute results found.";
  let md = `## Statute Results\n\n`;
  for (const r of results.slice(0, 10)) {
    md += `- **${r.number || r.title || "Section"}** — ${(r.name || r.text || "").slice(0, 200)}\n`;
  }
  return md;
}

function splitSentences(text: string): string[] {
  return text
    .replace(/\s+/g, " ")
    .split(/(?<=[.!?])\s+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function summarizeDocumentHeuristically(text: string): string {
  const sentences = splitSentences(text);
  if (sentences.length === 0) return "No content to summarize.";

  const legalKeywords = [
    "shall",
    "must",
    "liability",
    "indemnity",
    "termination",
    "governing law",
    "jurisdiction",
    "confidential",
    "notice",
    "obligation",
  ];

  const scored = sentences.map((sentence, index) => {
    const lower = sentence.toLowerCase();
    const keywordHits = legalKeywords.reduce((count, keyword) => count + (lower.includes(keyword) ? 1 : 0), 0);
    const lengthScore = Math.min(sentence.length / 180, 1);
    const leadBonus = index === 0 ? 0.5 : 0;
    return { sentence, index, score: keywordHits + lengthScore + leadBonus };
  });

  const selected = [...scored]
    .sort((a, b) => b.score - a.score || a.index - b.index)
    .slice(0, Math.min(4, sentences.length))
    .sort((a, b) => a.index - b.index)
    .map((row) => row.sentence);

  const words = text.match(/\b[\w'-]+\b/g) || [];
  return [
    "## Document Summary",
    "",
    ...selected.map((sentence) => `- ${sentence}`),
    "",
    `Source length: ${words.length.toLocaleString()} words across ${sentences.length} sentences.`,
  ].join("\n");
}

function analyzeDocument(text: string): string {
  const trimmed = text.trim();
  if (!trimmed) return "No content to analyze.";

  const paragraphs = trimmed.split(/\n\s*\n/).filter((item) => item.trim().length > 0);
  const sentences = splitSentences(trimmed);
  const words = trimmed.match(/\b[\w'-]+\b/g) || [];
  const unique = new Set(words.map((word) => word.toLowerCase()));
  const avgWordsPerSentence = sentences.length > 0 ? words.length / sentences.length : 0;

  const stopWords = new Set([
    "the", "and", "for", "with", "that", "this", "from", "into", "shall", "will", "are", "was", "were",
    "you", "your", "their", "our", "have", "has", "had", "not", "but", "all", "any", "may", "can", "its",
    "under", "within", "such", "each", "other",
  ]);
  const termFreq = new Map<string, number>();
  for (const word of words) {
    const token = word.toLowerCase();
    if (token.length < 4 || stopWords.has(token)) continue;
    termFreq.set(token, (termFreq.get(token) || 0) + 1);
  }
  const topTerms = Array.from(termFreq.entries())
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 8)
    .map(([term, count]) => `${term} (${count})`);

  const readability =
    avgWordsPerSentence < 16 ? "easy" : avgWordsPerSentence < 24 ? "moderate" : "dense";

  return [
    "## Document Analysis",
    "",
    `- Characters: ${trimmed.length.toLocaleString()}`,
    `- Words: ${words.length.toLocaleString()}`,
    `- Sentences: ${sentences.length.toLocaleString()}`,
    `- Paragraphs: ${paragraphs.length.toLocaleString()}`,
    `- Unique terms: ${unique.size.toLocaleString()}`,
    `- Avg words per sentence: ${avgWordsPerSentence.toFixed(1)} (${readability})`,
    "",
    topTerms.length > 0 ? `Top terms: ${topTerms.join(", ")}` : "Top terms: insufficient content.",
  ].join("\n");
}

function buildDueDiligenceReview(text: string): string {
  const lower = text.toLowerCase();
  const sections: Array<{ name: string; keywords: string[] }> = [
    { name: "Corporate authority", keywords: ["board", "director", "resolution", "authority", "incorporat"] },
    { name: "Commercial terms", keywords: ["payment", "fee", "price", "deliverable", "service level"] },
    { name: "Risk allocation", keywords: ["liability", "indemn", "warranty", "limitation", "force majeure"] },
    { name: "Termination mechanics", keywords: ["terminate", "notice", "breach", "cure", "expiry"] },
    { name: "Regulatory and privacy", keywords: ["compliance", "pdpa", "data protection", "consent", "regulator"] },
    { name: "Dispute framework", keywords: ["governing law", "jurisdiction", "arbitration", "mediation"] },
  ];

  const rows = sections.map((section) => {
    const hits = section.keywords.filter((keyword) => lower.includes(keyword)).length;
    const ratio = hits / section.keywords.length;
    const status = ratio >= 0.4 ? "covered" : ratio > 0 ? "partial" : "missing";
    return { ...section, hits, status };
  });

  const covered = rows.filter((row) => row.status === "covered").length;
  const partial = rows.filter((row) => row.status === "partial").length;
  const missing = rows.filter((row) => row.status === "missing").length;

  let md = "## Due Diligence Review\n\n";
  md += `Covered: ${covered} | Partial: ${partial} | Missing: ${missing}\n\n`;
  for (const row of rows) {
    md += `- **${row.name}**: ${row.status} (${row.hits}/${row.keywords.length} signals)\n`;
  }
  md += "\nNext steps:\n";
  md += "- Run `/check-compliance` on the same text.\n";
  md += "- Validate party authority and signature blocks.\n";
  md += "- Confirm governing law and dispute forum consistency.\n";
  return md;
}

async function draftClauseFromLibrary(query: string): Promise<string> {
  const data = await listClauses(query);
  const clauses = Array.isArray(data) ? data : [];
  if (clauses.length === 0) {
    return [
      "No matching clause found in the library.",
      "Try a more specific prompt like:",
      "- force majeure",
      "- limitation of liability",
      "- confidentiality",
      "",
      "Browse all clauses at `/clauses`.",
    ].join("\n");
  }

  const clause = clauses[0];
  const standard = String(clause.standard || "").slice(0, 900);
  const notes = clause.notes ? `\nNotes: ${String(clause.notes).slice(0, 300)}` : "";
  return [
    `## Draft Clause: ${clause.name}`,
    "",
    `Category: ${clause.category} | Jurisdiction: ${clause.jurisdiction}`,
    "",
    standard,
    "",
    "Alternate tones available: standard, aggressive, balanced, protective.",
    notes,
    "",
    "For more options, open `/clauses`.",
  ].join("\n");
}

async function listTemplateOptions(query: string): Promise<string> {
  const data = await listTemplates();
  const templates = Array.isArray(data) ? data : [];
  if (templates.length === 0) return "Template library is currently unavailable.";

  const normalized = query.trim().toLowerCase();
  const filtered = normalized
    ? templates.filter((template) => {
        const title = String(template.title || "").toLowerCase();
        const category = String(template.category || "").toLowerCase();
        const description = String(template.description || "").toLowerCase();
        return title.includes(normalized) || category.includes(normalized) || description.includes(normalized);
      })
    : templates;

  const list = filtered.slice(0, 8);
  if (list.length === 0) return `No templates matched "${query}". Browse all templates at \`/templates\`.`;

  let md = "## Template Library\n\n";
  for (const template of list) {
    md += `- **${template.title}** (${template.category}, ${template.jurisdiction})\n`;
  }
  md += "\nOpen `/templates` to render a document.";
  return md;
}

function compareDrafts(payload: string): string {
  const separators = ["\n---\n", "\n<<<>>>\n", "\n====\n", "\n***\n"];
  let original = "";
  let revised = "";
  for (const separator of separators) {
    if (payload.includes(separator)) {
      const [left, right] = payload.split(separator, 2);
      original = left.trim();
      revised = right.trim();
      break;
    }
  }

  if (!original || !revised) {
    return [
      "Redline input format is invalid.",
      "Provide two drafts separated by one of these delimiters:",
      "- `---`",
      "- `<<<>>>`",
      "- `====`",
    ].join("\n");
  }

  if (original === revised) {
    return "No differences detected between the two drafts.";
  }

  const originalLines = original.split("\n").map((line) => line.trim()).filter(Boolean);
  const revisedLines = revised.split("\n").map((line) => line.trim()).filter(Boolean);
  const originalSet = new Set(originalLines);
  const revisedSet = new Set(revisedLines);

  const removed = originalLines.filter((line) => !revisedSet.has(line));
  const added = revisedLines.filter((line) => !originalSet.has(line));

  let md = "## Redline Summary\n\n";
  md += `- Original lines: ${originalLines.length}\n`;
  md += `- Revised lines: ${revisedLines.length}\n`;
  md += `- Added lines: ${added.length}\n`;
  md += `- Removed lines: ${removed.length}\n\n`;

  if (added.length > 0) {
    md += "Added:\n";
    for (const line of added.slice(0, 8)) md += `- + ${line}\n`;
    if (added.length > 8) md += `- + ... ${added.length - 8} more lines\n`;
    md += "\n";
  }

  if (removed.length > 0) {
    md += "Removed:\n";
    for (const line of removed.slice(0, 8)) md += `- - ${line}\n`;
    if (removed.length > 8) md += `- - ... ${removed.length - 8} more lines\n`;
  }

  return md;
}
