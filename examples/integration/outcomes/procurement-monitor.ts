// Outcome: Procurement monitor.
// Mirrors examples/outcome-procurement-monitor.md.
// Run: npx tsx examples/integration/outcomes/procurement-monitor.ts "<sectorKeyword>"
import { callToolPayload, connectClient, exitOnError } from "./_shared.js";

const KEYWORD = process.argv[2] ?? "construction";

const main = async () => {
  const client = await connectClient("procurement-monitor");
  try {
    const tenders = await callToolPayload<{ records?: readonly Record<string, unknown>[] }>(client, "sg_gebiz_tenders", {
      keyword: KEYWORD,
      limit: 20,
    });
    const records = tenders.records ?? [];
    console.log(`\n=== GeBIZ tenders matching "${KEYWORD}" (${records.length}) ===`);
    for (const tender of records.slice(0, 10)) {
      const title = tender["title"] ?? tender["tenderTitle"] ?? "(untitled)";
      const agency = tender["agency"] ?? "(unknown agency)";
      const closing = tender["closingDate"] ?? tender["closing"] ?? "(no close date)";
      console.log(`  - ${title} | ${agency} | closes ${closing}`);
    }

    // Surface government-feed signals so monitors can correlate procurement chatter with announcements.
    const feeds = await callToolPayload<{ records?: readonly Record<string, unknown>[] }>(client, "sg_govfeeds_articles", {
      limit: 10,
    });
    console.log(`\n=== Recent gov feed announcements (${feeds.records?.length ?? 0}) ===`);
    for (const article of (feeds.records ?? []).slice(0, 5)) {
      console.log(`  - ${article["title"] ?? "(untitled)"} (${article["publishedAt"] ?? "?"})`);
    }
  } finally {
    await client.close();
  }
};

main().catch(exitOnError);
