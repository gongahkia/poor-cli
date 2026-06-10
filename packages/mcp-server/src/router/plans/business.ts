import type { BusinessDossierModule, BusinessSectorHint } from "../../diligence/entity-resolution.js";
import { selectBusinessDossierModules } from "../../diligence/entity-resolution.js";
import {
  buildBlockedPlan,
  createBlocker,
  type QueryPlan,
  type QueryStep,
} from "../planner-core.js";

const inferBusinessApis = (params: Readonly<Record<string, unknown>>): readonly string[] => {
  const modules = selectBusinessDossierModules(
    Array.isArray(params["modules"])
      ? params["modules"] as Parameters<typeof selectBusinessDossierModules>[0]
      : undefined,
    Array.isArray(params["sectorHints"])
      ? params["sectorHints"] as Parameters<typeof selectBusinessDossierModules>[1]
      : undefined,
  );

  return modules.map((module) => module === "gebiz" ? "gebiz" : module);
};

export const buildBusinessRegistryPlan = (
  params: Readonly<Record<string, unknown>>,
  options?: Readonly<{
    workflow?: string;
    confidence?: number;
    defaultModules?: readonly BusinessDossierModule[];
    defaultSectorHints?: readonly BusinessSectorHint[];
  }>,
): QueryPlan => {
  const entityName = typeof params["entityName"] === "string" ? params["entityName"] : undefined;
  const companyName = typeof params["companyName"] === "string" ? params["companyName"] : entityName;
  const estateAgentName = typeof params["estateAgentName"] === "string" ? params["estateAgentName"] : undefined;
  const acraName = estateAgentName ?? companyName;
  const uen = typeof params["uen"] === "string" ? params["uen"] : undefined;
  const salespersonName = typeof params["salespersonName"] === "string" ? params["salespersonName"] : undefined;
  const registrationNo = typeof params["registrationNo"] === "string" ? params["registrationNo"] : undefined;
  const estateAgentLicenseNo =
    typeof params["estateAgentLicenseNo"] === "string" ? params["estateAgentLicenseNo"] : undefined;
  const workhead = typeof params["workhead"] === "string" ? params["workhead"] : undefined;
  const grade = typeof params["grade"] === "string" ? params["grade"] : undefined;
  const classCode = typeof params["classCode"] === "string" ? params["classCode"] : undefined;
  const workflow = options?.workflow ?? "business_dossier";
  const modules = Array.isArray(params["modules"])
    ? params["modules"] as readonly BusinessDossierModule[]
    : [];
  const sectorHints = Array.isArray(params["sectorHints"])
    ? params["sectorHints"] as readonly BusinessSectorHint[]
    : [];
  const mergedModules = Array.from(new Set([
    ...(options?.defaultModules ?? []),
    ...modules,
  ]));
  const mergedSectorHints = Array.from(new Set([
    ...(options?.defaultSectorHints ?? []),
    ...sectorHints,
  ]));
  const dossierParams = {
    ...params,
    ...(mergedModules.length === 0 ? {} : { modules: mergedModules }),
    ...(mergedSectorHints.length === 0 ? {} : { sectorHints: mergedSectorHints }),
  };
  const apis = inferBusinessApis(dossierParams);

  const steps: QueryStep[] = [];

  if (
    salespersonName !== undefined
    || registrationNo !== undefined
    || estateAgentName !== undefined
    || estateAgentLicenseNo !== undefined
  ) {
    steps.push({
      id: "registry_cea",
      purpose: "Inspect CEA salesperson and estate-agent registration details.",
      tool: "sg_cea_salespersons",
      input: {
        ...(salespersonName === undefined ? {} : { salespersonName }),
        ...(registrationNo === undefined ? {} : { registrationNo }),
        ...(estateAgentName === undefined ? {} : { estateAgentName }),
        ...(estateAgentLicenseNo === undefined ? {} : { estateAgentLicenseNo }),
      },
    });
  }

  if (acraName !== undefined || uen !== undefined) {
    steps.push({
      id: "registry_acra",
      purpose: "Inspect ACRA corporate-entity registration details.",
      tool: "sg_acra_entities",
      input: {
        ...(acraName === undefined ? {} : { entityName: acraName }),
        ...(uen === undefined ? {} : { uen }),
      },
    });
  }

  if (companyName !== undefined || uen !== undefined || classCode !== undefined) {
    steps.push({
      id: "registry_bca_builders",
      purpose: "Check whether the entity appears on the BCA licensed-builders register.",
      tool: "sg_bca_licensed_builders",
      input: {
        ...(companyName === undefined ? {} : { companyName }),
        ...(uen === undefined ? {} : { uenNo: uen }),
        ...(classCode === undefined ? {} : { classCode }),
      },
    });
  }

  if (companyName !== undefined || uen !== undefined || workhead !== undefined || grade !== undefined) {
    steps.push({
      id: "registry_bca_contractors",
      purpose: "Check whether the entity appears on the BCA registered-contractors register.",
      tool: "sg_bca_registered_contractors",
      input: {
        ...(companyName === undefined ? {} : { companyName }),
        ...(uen === undefined ? {} : { uenNo: uen }),
        ...(workhead === undefined ? {} : { workhead }),
        ...(grade === undefined ? {} : { grade }),
      },
    });
  }

  if (steps.length === 0) {
    return buildBlockedPlan(
      {
        workflow,
        intent: "business",
        confidence: 0.78,
        apis,
        steps: [
          {
            id: "business_dossier",
            purpose: "Build a cross-registry business dossier once a business identifier is supplied.",
            tool: "sg_business_dossier",
            input: {
              ...(mergedModules.length === 0 ? {} : { modules: mergedModules }),
              ...(mergedSectorHints.length === 0 ? {} : { sectorHints: mergedSectorHints }),
            },
          },
        ],
      },
      [
        createBlocker(
          "entityName",
          "Provide a company or entity name to run the business dossier.",
          "sg_business_dossier",
          { entityName: "ABC CONSTRUCTION PTE LTD" },
          "Business dossier for ABC CONSTRUCTION PTE LTD",
        ),
        createBlocker(
          "uen",
          "Provide a UEN to run an exact registry dossier.",
          "sg_business_dossier",
          { uen: "201912345K" },
          "Business dossier for UEN 201912345K",
        ),
        createBlocker(
          "registrationNo",
          "Provide a salesperson registration number to inspect CEA records.",
          "sg_cea_salespersons",
          { registrationNo: "R123456A" },
          "Registry diligence for registration number R123456A",
        ),
      ],
      "sg_query needs a company name, entity name, UEN, salesperson, or estate-agent identifier to run registry diligence.",
      "Provide an explicit company or salesperson identifier, or call the direct ACRA, CEA, or BCA tool yourself.",
    );
  }

  return {
    supported: true,
    workflow,
    intent: "business",
    confidence: options?.confidence ?? 0.9,
    apis,
    steps: [
      {
        id: "business_dossier",
        purpose: "Build a cross-registry business dossier.",
        tool: "sg_business_dossier",
        input: {
          ...(acraName === undefined ? {} : { entityName: acraName }),
          ...(uen === undefined ? {} : { uen }),
          ...(salespersonName === undefined ? {} : { salespersonName }),
          ...(registrationNo === undefined ? {} : { registrationNo }),
          ...(estateAgentName === undefined ? {} : { estateAgentName }),
          ...(estateAgentLicenseNo === undefined ? {} : { estateAgentLicenseNo }),
          ...(classCode === undefined ? {} : { classCode }),
          ...(workhead === undefined ? {} : { workhead }),
          ...(grade === undefined ? {} : { grade }),
          ...(mergedModules.length === 0 ? {} : { modules: mergedModules }),
          ...(mergedSectorHints.length === 0 ? {} : { sectorHints: mergedSectorHints }),
        },
      },
    ],
  };
};
