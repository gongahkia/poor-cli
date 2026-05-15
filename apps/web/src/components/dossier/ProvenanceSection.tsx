import { formatTimestamp } from "@/lib/dossier";
import type { BriefFreshnessItem, BriefProvenanceItem, BusinessDossier } from "@/types/dossier";

const TOOL_FRESHNESS_SOURCES: Record<string, string> = {
  sg_acra_entities: "ACRA",
  sg_bca_licensed_builders: "BCA licensed builders",
  sg_bca_registered_contractors: "BCA registered contractors",
  sg_cea_salespersons: "CEA",
  sg_gebiz_tenders: "GeBIZ",
  sg_boa_architects: "BOA architects",
  sg_boa_architecture_firms: "BOA architecture firms",
  sg_hsa_licensed_pharmacies: "HSA licensed pharmacies",
  sg_hsa_health_product_licensees: "HSA health product licensees",
  sg_hlb_hotels: "HLB hotels",
};

const EVIDENCE_TYPE_LABELS: Record<NonNullable<BriefProvenanceItem["evidenceType"]>, string> = {
  official_registry: "Official registry evidence",
  operational_metadata: "Operational metadata",
  web_discovery: "Web discovery",
};

function getFreshness(dossier: BusinessDossier, provenance: BriefProvenanceItem): BriefFreshnessItem | undefined {
  const expectedSource = TOOL_FRESHNESS_SOURCES[provenance.tool] ?? provenance.source;
  const normalizedExpected = expectedSource.toLowerCase();
  const exact = dossier.freshness.find((item) => item.source.toLowerCase() === normalizedExpected);

  if (exact !== undefined) {
    return exact;
  }

  const normalizedSource = provenance.source.toLowerCase();
  return dossier.freshness.find((item) => item.source.toLowerCase().includes(normalizedSource));
}

function getEvidenceTypeLabel(item: BriefProvenanceItem): string {
  return EVIDENCE_TYPE_LABELS[item.evidenceType ?? "official_registry"];
}

export function ProvenanceSection({ dossier }: { dossier: BusinessDossier }) {
  return (
    <section className="min-w-0 rounded-lg border border-border bg-card p-4 shadow-sm sm:p-5">
      <h2 className="text-xl font-semibold tracking-normal text-foreground">Provenance</h2>
      <div className="mt-4 grid min-w-0 gap-3">
        {dossier.provenance.map((item) => {
          const freshness = getFreshness(dossier, item);
          const observedAt = formatTimestamp(freshness?.observedAt) ?? "Not available";
          const upstreamTimestamp = formatTimestamp(freshness?.upstreamTimestamp ?? null);

          return (
            <article className="min-w-0 rounded-md border border-border p-3" key={`${item.source}-${item.tool}`}>
              <div className="flex min-w-0 flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between">
                <h3 className="min-w-0 break-words font-medium text-foreground">{item.source}</h3>
                <p className="break-words text-xs text-muted-foreground sm:text-right">Checked by Dude: {observedAt}</p>
              </div>
              <p className="mt-2 break-words text-sm leading-6 text-muted-foreground">{item.coverage}</p>
              <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
                <span className="max-w-full break-words rounded-md bg-muted px-2 py-1">{getEvidenceTypeLabel(item)}</span>
                <span className="max-w-full break-all rounded-md bg-muted px-2 py-1">{item.tool}</span>
                <span className="rounded-md bg-muted px-2 py-1">{item.recordCount} records</span>
                <span className="rounded-md bg-muted px-2 py-1">
                  {item.authRequired ? "Auth required" : "No auth"}
                </span>
                <span className="max-w-full break-words rounded-md bg-muted px-2 py-1">
                  Source record date: {upstreamTimestamp ?? "Not provided"}
                </span>
                {item.sourceUrl !== undefined ? (
                  <a
                    className="max-w-full break-all rounded-md bg-muted px-2 py-1 underline-offset-4 hover:underline"
                    href={item.sourceUrl}
                    rel="noreferrer"
                    target="_blank"
                  >
                    Open source
                  </a>
                ) : null}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
