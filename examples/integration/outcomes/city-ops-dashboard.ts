// Outcome: City operations dashboard.
// Run: npx tsx examples/integration/outcomes/city-ops-dashboard.ts Bedok
import { callToolPayload, connectClient, exitOnError, renderPulseSnapshot } from "./_shared.js";

const AREA = process.argv[2] ?? "Bedok";

const main = async () => {
  const client = await connectClient("city-ops-dashboard");
  try {
    const payload = await callToolPayload<{ snapshot: Record<string, unknown> }>(client, "swee_pulse_snapshot", {
      focus: "all",
      area: AREA,
    });
    renderPulseSnapshot(`Swee Pulse for ${AREA}`, payload.snapshot as Parameters<typeof renderPulseSnapshot>[1]);

    const audits = await callToolPayload<{ records?: readonly Record<string, unknown>[] }>(client, "swee_shield_audit_lookup", {
      limit: 5,
    });
    console.log("\n=== Recent Shield audits ===");
    for (const audit of audits.records ?? []) {
      console.log(`  - ${audit["toolName"] ?? "(unknown tool)"} | ${audit["decision"] ?? "(no decision)"} | ${audit["status"] ?? "(no status)"}`);
    }
  } finally {
    await client.close();
  }
};

main().catch(exitOnError);
