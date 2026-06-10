import { describe, expect, it } from "vitest";
import { classifyIntent } from "../../router/classifier.js";
import { planQuery } from "../../router/planner.js";

describe("CDD Pipeline", () => {
  it("routes company dossier prompts to business diligence", () => {
    const intent = classifyIntent("Business dossier for ABC CONSTRUCTION PTE LTD");
    expect(intent.intent).toBe("business");
    expect(intent.workflow).toBe("business_registry_diligence");
    expect(intent.extractedParams["entityName"]).toBe("ABC CONSTRUCTION PTE LTD");
  });

  it("builds a company CDD query plan", () => {
    const plan = planQuery("Business dossier for ABC CONSTRUCTION PTE LTD");
    expect(plan.supported).toBe(true);
    if (plan.supported) {
      expect(plan.workflow).toBe("business_dossier");
      expect(plan.steps.map((step) => step.tool)).toEqual(["sg_business_dossier"]);
    }
  });

  it("blocks CDD prompts without a company or registry identifier", () => {
    const plan = planQuery("Run business diligence");
    expect(plan.supported).toBe(false);
    if (!plan.supported && plan.blocked === true) {
      expect(plan.workflow).toBe("business_dossier");
      expect(plan.blockers.map((blocker) => blocker.field)).toEqual(
        expect.arrayContaining(["entityName", "uen", "registrationNo"]),
      );
    }
  });

  it("routes architecture-firm prompts to the BOA-enriched workflow", () => {
    const plan = planQuery("Architecture firm diligence for DP Architects");
    expect(plan.supported).toBe(true);
    if (plan.supported) {
      expect(plan.workflow).toBe("architecture_firm_diligence");
      expect(plan.steps[0]?.input).toMatchObject({
        entityName: "DP Architects",
        modules: expect.arrayContaining(["acra", "boa", "gebiz"]),
      });
    }
  });

  it("routes healthcare supplier prompts to the HSA-enriched workflow", () => {
    const plan = planQuery("Healthcare supplier diligence for ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD.");
    expect(plan.supported).toBe(true);
    if (plan.supported) {
      expect(plan.workflow).toBe("healthcare_supplier_diligence");
      expect(plan.steps[0]?.input).toMatchObject({
        modules: expect.arrayContaining(["acra", "hsa", "gebiz"]),
      });
    }
  });

  it("rejects removed non-CDD public-data plans", () => {
    const plan = planQuery("Search for GDP datasets");
    expect(plan.supported).toBe(false);
    if (!plan.supported) {
      expect(plan.reason).toContain("CDD entity and sector diligence");
    }
  });
});
