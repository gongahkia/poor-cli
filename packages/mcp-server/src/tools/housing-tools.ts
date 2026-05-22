import {
  HousingAffordabilitySchema,
  HousingGrantEligibilitySchema,
  HousingLoanCompareSchema,
  HousingResaleCompareSchema,
  formatResponse,
  validateInput,
} from "@swee-sg/shared";
import type { ToolResult } from "@swee-sg/shared";
import { computeAffordability } from "../housing/affordability.js";
import { computeGrantEligibility } from "../housing/grants.js";
import type { HouseholdProfile } from "../housing/grants.js";
import { compareLoans } from "../housing/loans.js";
import type { BankPackage } from "../housing/loans.js";
import { compareResalePrice } from "../housing/resale-compare.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

const renderJson = (payload: Readonly<Record<string, unknown>>): string => {
  return formatResponse(payload as Record<string, unknown>, "json");
};

const renderMarkdown = (payload: Readonly<Record<string, unknown>>, title: string): string => {
  return `## ${title}\n\n\`\`\`json\n${JSON.stringify(payload, null, 2)}\n\`\`\``;
};

const toResult = (
  payload: Readonly<Record<string, unknown>>,
  format: "json" | "markdown" | undefined,
  title: string,
): ToolResult => {
  const fmt = format ?? "json";
  return {
    content: [{
      type: "text",
      text: fmt === "markdown" ? renderMarkdown(payload, title) : renderJson(payload),
    }],
    structuredContent: payload,
  };
};

export const handleGrantEligibility = async (
  params: Readonly<{
    profile: HouseholdProfile;
    format?: "json" | "markdown" | undefined;
  }>,
): Promise<ToolResult> => {
  const result = computeGrantEligibility(params.profile);
  return toResult(result as unknown as Readonly<Record<string, unknown>>, params.format, "HDB Grant Eligibility");
};

export const handleLoanCompare = async (
  params: Readonly<{
    priceSgd: number;
    downpaymentSgd: number;
    tenureYears: number;
    soraValue?: number | undefined;
    soraTenor?: "1m" | "3m" | undefined;
    bankPackages?: readonly BankPackage[] | undefined;
    includeHdbLoan?: boolean | undefined;
    format?: "json" | "markdown" | undefined;
  }>,
): Promise<ToolResult> => {
  const result = compareLoans({
    priceSgd: params.priceSgd,
    downpaymentSgd: params.downpaymentSgd,
    tenureYears: params.tenureYears,
    ...(params.soraValue === undefined ? {} : { soraValue: params.soraValue }),
    ...(params.soraTenor === undefined ? {} : { soraTenor: params.soraTenor }),
    ...(params.bankPackages === undefined ? {} : { bankPackages: params.bankPackages }),
    ...(params.includeHdbLoan === undefined ? {} : { includeHdbLoan: params.includeHdbLoan }),
  });
  return toResult(result as unknown as Readonly<Record<string, unknown>>, params.format, "Loan Comparison");
};

export const handleAffordability = async (
  params: Readonly<{
    profile: HouseholdProfile;
    targetPriceSgd: number;
    tenureYears: number;
    cashOnHandSgd: number;
    cpfOaBalanceSgd: number;
    otherMonthlyDebtSgd?: number | undefined;
    soraValue?: number | undefined;
    bankPackages?: readonly BankPackage[] | undefined;
    loanType?: "hdb" | "bank" | undefined;
    format?: "json" | "markdown" | undefined;
  }>,
): Promise<ToolResult> => {
  const result = computeAffordability({
    profile: params.profile,
    targetPriceSgd: params.targetPriceSgd,
    tenureYears: params.tenureYears,
    cashOnHandSgd: params.cashOnHandSgd,
    cpfOaBalanceSgd: params.cpfOaBalanceSgd,
    ...(params.otherMonthlyDebtSgd === undefined ? {} : { otherMonthlyDebtSgd: params.otherMonthlyDebtSgd }),
    ...(params.soraValue === undefined ? {} : { soraValue: params.soraValue }),
    ...(params.bankPackages === undefined ? {} : { bankPackages: params.bankPackages }),
    ...(params.loanType === undefined ? {} : { loanType: params.loanType }),
  });
  return toResult(result as unknown as Readonly<Record<string, unknown>>, params.format, "Housing Affordability");
};

export const handleResaleCompare = async (
  params: Readonly<{
    town: string;
    flatType: string;
    askingPriceSgd: number;
    storeyBand?: string | undefined;
    remainingLeaseYears?: number | undefined;
    lookbackMonths?: number | undefined;
    format?: "json" | "markdown" | undefined;
  }>,
): Promise<ToolResult> => {
  const result = await compareResalePrice({
    town: params.town,
    flatType: params.flatType,
    askingPriceSgd: params.askingPriceSgd,
    ...(params.storeyBand === undefined ? {} : { storeyBand: params.storeyBand }),
    ...(params.remainingLeaseYears === undefined ? {} : { remainingLeaseYears: params.remainingLeaseYears }),
    ...(params.lookbackMonths === undefined ? {} : { lookbackMonths: params.lookbackMonths }),
  });
  return toResult(result as unknown as Readonly<Record<string, unknown>>, params.format, "Resale Price Comparison");
};

export const housingToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_grant_eligibility",
    description: "Compute HDB/CPF housing grant eligibility (EHG, Family, Singles, Proximity, Step-Up) from a household profile. Deterministic; uses embedded versioned rules. Banks do not issue HDB grants.",
    surface: "canonical",
    inputSchema: HousingGrantEligibilitySchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleGrantEligibility(validateInput(HousingGrantEligibilitySchema, input)),
  },
  {
    name: "sg_loan_compare",
    description: "Compare HDB concessionary loan vs caller-supplied bank packages. Pass live SORA from sg_mas_interest_rates. Outputs monthly instalment, blended interest estimate, and best-by-year-1/lifetime.",
    surface: "canonical",
    inputSchema: HousingLoanCompareSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleLoanCompare(validateInput(HousingLoanCompareSchema, input)),
  },
  {
    name: "sg_housing_affordability",
    description: "Integrated BTO/resale affordability check: TDSR (55%) + MSR (30%) + LTV cap, downpayment cash/CPF split, BSD, grants, and verdict (fits/tight/over_budget).",
    surface: "canonical",
    inputSchema: HousingAffordabilitySchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleAffordability(validateInput(HousingAffordabilitySchema, input)),
  },
  {
    name: "sg_resale_price_compare",
    description: "Benchmark a target resale unit against recent transactions in the same town/flat-type via data.gov.sg HDB resale dataset. Outputs median/IQR, variance %, and verdict.",
    surface: "canonical",
    inputSchema: HousingResaleCompareSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleResaleCompare(validateInput(HousingResaleCompareSchema, input)),
  },
];
