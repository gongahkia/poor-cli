// Outcome: Outdoor event readiness checker.
// Mirrors examples/outcome-outdoor-event-checker.md.
// Run: npx tsx examples/integration/outcomes/outdoor-event-checker.ts <area>
import { callToolPayload, connectClient, exitOnError, renderBrief } from "./_shared.js";

const AREA = process.argv[2] ?? "Bedok";

const main = async () => {
  const client = await connectClient("outdoor-event-checker");
  try {
    const env = await callToolPayload(client, "sg_environment_brief", {
      area: AREA,
      format: "json",
    });
    renderBrief(`Environment for ${AREA}`, env as never);

    const transport = await callToolPayload(client, "sg_transport_brief", { format: "json" });
    renderBrief("Transport snapshot", transport as never);

    // Decision: surface a single go / hold / cancel verdict drawn from existing risk flags.
    const flags = (env as { riskFlags?: { severity: string; code: string }[] }).riskFlags ?? [];
    const high = flags.filter((flag) => flag.severity === "high");
    const verdict = high.length > 0 ? "HOLD or CANCEL" : flags.length > 0 ? "PROCEED WITH CAUTION" : "CLEAR";
    console.log(`\nVerdict for outdoor event in ${AREA}: ${verdict}`);
    if (flags.length > 0) {
      console.log(`Drivers: ${flags.map((flag) => flag.code).join(", ")}`);
    }
  } finally {
    await client.close();
  }
};

main().catch(exitOnError);
