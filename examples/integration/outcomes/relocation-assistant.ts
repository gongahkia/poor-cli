// Outcome: Relocation Assistant.
// Mirrors examples/outcome-relocation-assistant.md.
// Run: npx tsx examples/integration/outcomes/relocation-assistant.ts <postalCode>
import { callToolPayload, connectClient, exitOnError, renderBrief } from "./_shared.js";

const POSTAL_CODE = process.argv[2] ?? "460123";

const main = async () => {
  const client = await connectClient("relocation-assistant");
  try {
    const property = await callToolPayload(client, "sg_property_brief", {
      postalCode: POSTAL_CODE,
      includeTransport: true,
      includeEnvironment: true,
      format: "json",
    });
    renderBrief("Property + transport + environment", property as never);

    const civic = await callToolPayload(client, "sg_civic_brief", {
      postalCode: POSTAL_CODE,
      radiusKm: 1.5,
      format: "json",
    });
    renderBrief("Civic services within 1.5 km", civic as never);

    const transport = await callToolPayload(client, "sg_transport_brief", { format: "json" });
    renderBrief("Live transport snapshot", transport as never);

    const environment = await callToolPayload(client, "sg_environment_brief", { format: "json" });
    renderBrief("Live environment snapshot", environment as never);
  } finally {
    await client.close();
  }
};

main().catch(exitOnError);
