// Outcome: SME diligence dashboard.
// Mirrors examples/outcome-sme-diligence-dashboard.md.
// Run: npx tsx examples/integration/outcomes/sme-diligence-dashboard.ts "<companyNameOrUEN>"
import { callToolPayload, connectClient, exitOnError, renderBrief } from "./_shared.js";

const TARGET = process.argv[2] ?? "DP ARCHITECTS PTE LTD";

const main = async () => {
  const client = await connectClient("sme-diligence-dashboard");
  try {
    const dossier = await callToolPayload(client, "sg_business_dossier", {
      companyName: TARGET,
      format: "json",
    });
    renderBrief("Business registry dossier", dossier as never);

    // Run a tender lookup against the same company name as a follow-up signal.
    const tenders = await callToolPayload<{ records?: readonly Record<string, unknown>[] }>(client, "sg_gebiz_tenders", {
      keyword: TARGET.split(" ")[0],
      limit: 5,
    });
    console.log(`\n=== Recent GeBIZ tenders matching "${TARGET.split(" ")[0]}" ===`);
    for (const tender of tenders.records ?? []) {
      console.log(`  - ${tender["title"] ?? tender["tenderTitle"] ?? "(untitled)"}`);
    }
  } finally {
    await client.close();
  }
};

main().catch(exitOnError);
