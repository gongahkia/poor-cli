import { classifyIntent, resolveToolInput } from "./classifier.js";
import { buildUnsupportedPlan, type QueryPlan } from "./planner-core.js";
import { buildBusinessRegistryPlan } from "./plans/business.js";

export type { QueryExecutionContext, QueryPlan, QueryStep } from "./planner-core.js";

const CDD_ONLY_REASON = "Dude now supports CDD entity and sector diligence workflows only.";
const CDD_ONLY_SUGGESTION =
  "Search a Singapore company name or UEN, or ask for architecture, healthcare, hotel, contractor, CEA, HSA, HLB, BOA, BCA, ACRA, or GeBIZ evidence.";

const CDD_QUERY_TOOLS = new Set([
  "sg_acra_entities",
  "sg_bca_licensed_builders",
  "sg_bca_registered_contractors",
  "sg_boa_architects",
  "sg_boa_architecture_firms",
  "sg_cea_salespersons",
  "sg_business_dossier",
  "sg_gebiz_tenders",
  "sg_hsa_licensed_pharmacies",
  "sg_hsa_health_product_licensees",
  "sg_hlb_hotels",
]);

const buildDirectCddToolPlan = (query: string): QueryPlan => {
  const intent = classifyIntent(query);
  if (intent.tool === undefined || !CDD_QUERY_TOOLS.has(intent.tool)) {
    return buildUnsupportedPlan(CDD_ONLY_REASON, CDD_ONLY_SUGGESTION);
  }

  const resolved = resolveToolInput(intent, query);
  return {
    supported: true,
    workflow: "direct_tool",
    intent: intent.intent,
    confidence: intent.confidence,
    apis: intent.apis,
    steps: [
      {
        id: "direct_tool",
        purpose: `Execute ${resolved.tool}.`,
        tool: resolved.tool,
        input: resolved.input,
      },
    ],
  };
};

export const planQuery = (query: string): QueryPlan => {
  const intent = classifyIntent(query);

  switch (intent.workflow) {
    case "business_registry_diligence":
      return buildBusinessRegistryPlan(intent.extractedParams);
    case "architecture_firm_diligence":
      return buildBusinessRegistryPlan(intent.extractedParams, {
        workflow: "architecture_firm_diligence",
        confidence: intent.confidence,
        defaultModules: ["acra", "boa", "gebiz"],
      });
    case "healthcare_supplier_diligence":
      return buildBusinessRegistryPlan(intent.extractedParams, {
        workflow: "healthcare_supplier_diligence",
        confidence: intent.confidence,
        defaultModules: ["acra", "hsa", "gebiz"],
      });
    case "hotel_operator_lookup":
      return buildBusinessRegistryPlan(intent.extractedParams, {
        workflow: "hotel_operator_lookup",
        confidence: intent.confidence,
        defaultModules: ["acra", "hlb"],
      });
    case "sector_scoped_business_diligence":
      return buildBusinessRegistryPlan(intent.extractedParams, {
        workflow: "sector_scoped_business_diligence",
        confidence: intent.confidence,
      });
    case "direct_tool":
      return buildDirectCddToolPlan(query);
    default:
      return buildUnsupportedPlan(CDD_ONLY_REASON, CDD_ONLY_SUGGESTION);
  }
};
