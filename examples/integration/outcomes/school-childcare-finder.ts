// Outcome: School + childcare finder for family relocation.
// Mirrors examples/outcome-school-childcare-finder.md.
// Run: npx tsx examples/integration/outcomes/school-childcare-finder.ts <postalCode>
import { callToolPayload, connectClient, exitOnError, renderBrief } from "./_shared.js";

const POSTAL_CODE = process.argv[2] ?? "560123";

const main = async () => {
  const client = await connectClient("school-childcare-finder");
  try {
    const civic = await callToolPayload(client, "sg_civic_brief", {
      postalCode: POSTAL_CODE,
      radiusKm: 2,
      format: "json",
    });
    renderBrief("Civic facilities (childcare, MSF, sport)", civic as never);

    const geocode = await callToolPayload<{ records?: { lat: number; lng: number }[] }>(client, "sg_onemap_geocode", {
      searchVal: POSTAL_CODE,
      pageNum: 1,
    });
    const point = geocode.records?.[0];
    if (point === undefined) {
      console.log("Could not geocode postal code; cannot run school discovery.");
      return;
    }
    const schools = await callToolPayload<{ records?: readonly Record<string, unknown>[] }>(client, "sg_moe_schools", {
      lat: point.lat,
      lng: point.lng,
      radiusKm: 2,
      limit: 10,
    });
    console.log(`\n=== MOE schools within 2 km of ${POSTAL_CODE} ===`);
    for (const school of schools.records ?? []) {
      console.log(`  - ${school["name"] ?? school["schoolName"] ?? "(unnamed)"}`);
    }

    const childcare = await callToolPayload<{ records?: readonly Record<string, unknown>[] }>(client, "sg_ecda_childcare_centres", {
      lat: point.lat,
      lng: point.lng,
      radiusKm: 2,
      limit: 10,
    });
    console.log(`\n=== ECDA childcare centres within 2 km of ${POSTAL_CODE} ===`);
    for (const centre of childcare.records ?? []) {
      console.log(`  - ${centre["centreName"] ?? centre["name"] ?? "(unnamed)"}`);
    }
  } finally {
    await client.close();
  }
};

main().catch(exitOnError);
